use std::fs::File;
use std::io::BufReader;
use std::sync::mpsc::{self, RecvTimeoutError, SyncSender};
use std::sync::{Arc, Mutex};
use std::time::Duration;

use cpal::traits::{DeviceTrait, HostTrait};
use rodio::{Decoder, Sink};
use tracing::{error, warn};

use crate::commands::{AudioOutputDevice, PlaybackState, TrackRecord};
use crate::errors::LyraResult;

/// List all available audio output devices on the host.
/// Returns an empty vec (not an error) if the host cannot be queried.
pub fn enumerate_output_devices() -> Vec<AudioOutputDevice> {
    let host = cpal::default_host();
    let default_name = host
        .default_output_device()
        .and_then(|d| d.name().ok())
        .unwrap_or_default();
    match host.output_devices() {
        Ok(devices) => devices
            .filter_map(|d| {
                let name = d.name().ok()?;
                let is_default = name == default_name;
                Some(AudioOutputDevice {
                    id: name.clone(),
                    name,
                    is_default,
                })
            })
            .collect(),
        Err(e) => {
            warn!("enumerate_output_devices failed: {e}");
            Vec::new()
        }
    }
}

enum AudioCommand {
    Play { path: String, volume: f32 },
    Stop,
    Pause,
    Resume,
    SetVolume(f32),
    Seek(f64),
}

#[derive(Default)]
struct SharedAudioState {
    position_seconds: f64,
    finished: bool,
}

struct AudioHandle {
    tx: SyncSender<AudioCommand>,
    state: Arc<Mutex<SharedAudioState>>,
}

impl AudioHandle {
    fn spawn_with_device(device_name: Option<&str>) -> Self {
        let (tx, rx) = mpsc::sync_channel::<AudioCommand>(16);
        let state = Arc::new(Mutex::new(SharedAudioState::default()));
        let state_clone = Arc::clone(&state);
        let device_name_owned: Option<String> = device_name.map(|s| s.to_string());

        std::thread::Builder::new()
            .name("lyra-audio".to_string())
            .spawn(move || {
                // Open the initial stream for the requested device.
                let mut stream_result = open_output_stream(device_name_owned.as_deref());
                if stream_result.is_err() && device_name_owned.is_some() {
                    warn!("lyra-audio: requested device unavailable, falling back to default");
                    stream_result = open_output_stream(None);
                }
                let Ok((_stream, stream_handle)) = stream_result else {
                    error!("lyra-audio: no audio output device available");
                    return;
                };
                let mut current_sink: Option<Sink> = None;

                loop {
                    match rx.recv_timeout(Duration::from_millis(250)) {
                        Ok(cmd) => match cmd {
                            AudioCommand::Play { path, volume } => {
                                if let Some(old) = current_sink.take() {
                                    old.stop();
                                }
                                match File::open(&path).map(BufReader::new) {
                                    Ok(reader) => match Decoder::new(reader) {
                                        Ok(source) => match Sink::try_new(&stream_handle) {
                                            Ok(sink) => {
                                                sink.set_volume(volume);
                                                sink.append(source);
                                                if let Ok(mut s) = state_clone.lock() {
                                                    s.position_seconds = 0.0;
                                                    s.finished = false;
                                                }
                                                current_sink = Some(sink);
                                            }
                                            Err(e) => error!("lyra-audio: sink create failed: {e}"),
                                        },
                                        Err(e) => {
                                            error!("lyra-audio: decode failed for {path}: {e}")
                                        }
                                    },
                                    Err(e) => {
                                        error!("lyra-audio: file open failed for {path}: {e}")
                                    }
                                }
                            }
                            AudioCommand::Stop => {
                                if let Some(old) = current_sink.take() {
                                    old.stop();
                                }
                                if let Ok(mut s) = state_clone.lock() {
                                    s.position_seconds = 0.0;
                                    s.finished = false;
                                }
                            }
                            AudioCommand::Pause => {
                                if let Some(s) = &current_sink {
                                    s.pause();
                                }
                            }
                            AudioCommand::Resume => {
                                if let Some(s) = &current_sink {
                                    s.play();
                                }
                            }
                            AudioCommand::SetVolume(vol) => {
                                if let Some(s) = &current_sink {
                                    s.set_volume(vol);
                                }
                            }
                            AudioCommand::Seek(secs) => {
                                if let Some(s) = &current_sink {
                                    let _ = s.try_seek(Duration::from_secs_f64(secs));
                                }
                            }
                        },
                        Err(RecvTimeoutError::Timeout) => {}
                        Err(RecvTimeoutError::Disconnected) => break,
                    }

                    if let Some(sink) = &current_sink {
                        if let Ok(mut s) = state_clone.lock() {
                            s.position_seconds = sink.get_pos().as_secs_f64();
                            s.finished = sink.empty();
                        }
                    }
                }
            })
            .expect("failed to spawn lyra-audio thread");

        Self { tx, state }
    }

    /// Spawn on the default output device.
    fn spawn() -> Self {
        Self::spawn_with_device(None)
    }

    fn send(&self, cmd: AudioCommand) {
        let _ = self.tx.send(cmd);
    }

    fn position_seconds(&self) -> f64 {
        self.state.lock().map(|s| s.position_seconds).unwrap_or(0.0)
    }

    fn is_finished(&self) -> bool {
        self.state.lock().map(|s| s.finished).unwrap_or(false)
    }
}

pub struct PlaybackController {
    current_track: Option<TrackRecord>,
    audio: AudioHandle,
    preferred_device: Option<String>,
}

impl PlaybackController {
    pub fn new(_playback_state: PlaybackState) -> LyraResult<Self> {
        Ok(Self {
            current_track: None,
            audio: AudioHandle::spawn(),
            preferred_device: None,
        })
    }

    pub fn snapshot(&self, mut base: PlaybackState) -> PlaybackState {
        if self.current_track.is_some() {
            // Active track in the audio engine: use live position and track info.
            base.current_track = self.current_track.clone();
            base.position_seconds = self.audio.position_seconds();
        }
        // When current_track is None (session-restored, not yet played in this
        // session), preserve the persisted position_seconds from SQLite so the
        // frontend shows the correct resume point.
        base.seek_supported = true;
        base
    }

    pub fn play_track(&mut self, track: TrackRecord, volume: f64) -> LyraResult<PlaybackState> {
        // Reset eagerly before sending to avoid double-advance race
        if let Ok(mut s) = self.audio.state.lock() {
            s.position_seconds = 0.0;
            s.finished = false;
        }
        self.audio.send(AudioCommand::Play {
            path: track.path.clone(),
            volume: volume as f32,
        });
        let duration_seconds = track.duration_seconds;
        self.current_track = Some(track.clone());
        Ok(PlaybackState {
            status: "playing".to_string(),
            current_track_id: Some(track.id),
            current_track: Some(track),
            queue_index: 0,
            position_seconds: 0.0,
            duration_seconds,
            volume,
            shuffle: false,
            repeat_mode: "off".to_string(),
            seek_supported: true,
        })
    }

    pub fn stop(&mut self, volume: f64) -> PlaybackState {
        self.audio.send(AudioCommand::Stop);
        self.current_track = None;
        PlaybackState {
            status: "idle".to_string(),
            current_track_id: None,
            current_track: None,
            queue_index: 0,
            position_seconds: 0.0,
            duration_seconds: 0.0,
            volume,
            shuffle: false,
            repeat_mode: "off".to_string(),
            seek_supported: true,
        }
    }

    pub fn toggle(&mut self, mut current: PlaybackState) -> LyraResult<PlaybackState> {
        if current.status == "playing" {
            self.audio.send(AudioCommand::Pause);
            current.status = "paused".to_string();
        } else {
            self.audio.send(AudioCommand::Resume);
            current.status = "playing".to_string();
        }
        Ok(current)
    }

    pub fn seek_to(
        &mut self,
        mut current: PlaybackState,
        position_seconds: f64,
    ) -> LyraResult<PlaybackState> {
        self.audio.send(AudioCommand::Seek(position_seconds));
        current.position_seconds = position_seconds;
        Ok(current)
    }

    pub fn set_volume(
        &mut self,
        mut current: PlaybackState,
        volume: f64,
    ) -> LyraResult<PlaybackState> {
        let clamped = volume.clamp(0.0, 1.0);
        self.audio.send(AudioCommand::SetVolume(clamped as f32));
        current.volume = clamped;
        Ok(current)
    }

    pub fn is_finished(&self) -> bool {
        self.audio.is_finished()
    }

    /// Returns true when the audio engine has an active (in-memory) track
    /// loaded, meaning playback can be paused/resumed without re-loading.
    pub fn has_active_track(&self) -> bool {
        self.current_track.is_some()
    }

    /// Switch the audio output device.  The current track is stopped; the
    /// caller must resume playback after calling this.
    pub fn set_output_device(&mut self, device_name: Option<String>) {
        self.current_track = None;
        self.preferred_device = device_name.clone();
        self.audio = AudioHandle::spawn_with_device(device_name.as_deref());
    }

    /// Return the currently preferred output device name (None = default).
    pub fn preferred_device(&self) -> Option<&str> {
        self.preferred_device.as_deref()
    }
}

/// Open a rodio `OutputStream` bound to the named device, or the default
/// device when `device_name` is `None`.
fn open_output_stream(
    device_name: Option<&str>,
) -> Result<(rodio::OutputStream, rodio::OutputStreamHandle), rodio::StreamError> {
    let Some(name) = device_name else {
        return rodio::OutputStream::try_default();
    };
    let host = cpal::default_host();
    let device = host
        .output_devices()
        .ok()
        .and_then(|mut devs| devs.find(|d| d.name().as_deref().unwrap_or("") == name));
    match device {
        Some(dev) => rodio::OutputStream::try_from_device(&dev),
        None => rodio::OutputStream::try_default(),
    }
}
