/// Windows System Media Transport Controls (SMTC) bridge.
///
/// Registers Lyra with the Windows taskbar / lock-screen media overlay.
/// Button events from the OS drive `LyraCore` directly (no round-trip
/// through the renderer), so the player stays responsive even when the
/// window is hidden.
#[cfg(target_os = "windows")]
pub use imp::SmtcBridge;

#[cfg(target_os = "windows")]
mod imp {
    use lyra_core::{commands::PlaybackState, LyraCore};
    use raw_window_handle::{HasWindowHandle, RawWindowHandle};
    use tracing::{error, info, warn};
    use windows::{
        core::{factory, HSTRING},
        Foundation::TypedEventHandler,
        Media::{
            MediaPlaybackStatus, MediaPlaybackType, SystemMediaTransportControls,
            SystemMediaTransportControlsButton,
            SystemMediaTransportControlsButtonPressedEventArgs,
        },
        Win32::{Foundation::HWND, System::WinRT::ISystemMediaTransportControlsInterop},
    };

    pub struct SmtcBridge {
        controls: SystemMediaTransportControls,
    }

    // SAFETY: WinRT objects are agile (apartment-neutral) by design.
    unsafe impl Send for SmtcBridge {}
    unsafe impl Sync for SmtcBridge {}

    impl SmtcBridge {
        /// Create an SMTC bridge for `window`.  Returns `None` on failure so
        /// the application starts normally even if SMTC is unavailable.
        pub fn new<W: HasWindowHandle>(window: &W, core: LyraCore) -> Option<Self> {
            let hwnd = Self::extract_hwnd(window)?;
            match Self::try_new(hwnd, core) {
                Ok(bridge) => {
                    info!("SMTC bridge initialised");
                    Some(bridge)
                }
                Err(e) => {
                    warn!("SMTC bridge could not be created: {e}");
                    None
                }
            }
        }

        fn extract_hwnd<W: HasWindowHandle>(window: &W) -> Option<HWND> {
            let handle = window.window_handle().ok()?;
            match handle.as_raw() {
                RawWindowHandle::Win32(h) => {
                    Some(HWND(h.hwnd.get() as *mut core::ffi::c_void))
                }
                _ => None,
            }
        }

        fn try_new(hwnd: HWND, core: LyraCore) -> windows::core::Result<Self> {
            let interop = factory::<
                SystemMediaTransportControls,
                ISystemMediaTransportControlsInterop,
            >()?;
            let controls: SystemMediaTransportControls =
                unsafe { interop.GetForWindow(hwnd)? };

            controls.SetIsEnabled(true)?;
            controls.SetIsPlayEnabled(true)?;
            controls.SetIsPauseEnabled(true)?;
            controls.SetIsNextEnabled(true)?;
            controls.SetIsPreviousEnabled(true)?;
            controls.SetIsStopEnabled(true)?;

            // Button presses go directly to core so they work when the
            // window is hidden (tray-only mode).
            controls.ButtonPressed(&TypedEventHandler::new(
                move |_smtc,
                      args: &Option<
                    SystemMediaTransportControlsButtonPressedEventArgs,
                >| {
                    let Some(args) = args else { return Ok(()) };
                    match args.Button()? {
                        SystemMediaTransportControlsButton::Play
                        | SystemMediaTransportControlsButton::Pause => {
                            let _ = core.toggle_playback();
                        }
                        SystemMediaTransportControlsButton::Next => {
                            let _ = core.play_next();
                        }
                        SystemMediaTransportControlsButton::Previous => {
                            let _ = core.play_previous();
                        }
                        SystemMediaTransportControlsButton::Stop => {
                            let _ = core.stop_playback();
                        }
                        _ => {}
                    }
                    Ok(())
                },
            ))?;

            Ok(Self { controls })
        }

        /// Update the OS overlay from the latest playback state.
        /// Called from the ticker thread; silently ignored on failure.
        pub fn update(&self, playback: &PlaybackState) {
            if let Err(e) = self.try_update(playback) {
                error!("SMTC update failed: {e}");
            }
        }

        fn try_update(&self, playback: &PlaybackState) -> windows::core::Result<()> {
            let status = match playback.status.as_str() {
                "playing" => MediaPlaybackStatus::Playing,
                "paused" => MediaPlaybackStatus::Paused,
                "stopped" => MediaPlaybackStatus::Stopped,
                _ => MediaPlaybackStatus::Closed,
            };
            self.controls.SetPlaybackStatus(status)?;

            if let Some(track) = &playback.current_track {
                let updater = self.controls.DisplayUpdater()?;
                updater.SetType(MediaPlaybackType::Music)?;
                let props = updater.MusicProperties()?;
                props.SetTitle(&HSTRING::from(track.title.as_str()))?;
                props.SetArtist(&HSTRING::from(track.artist.as_str()))?;
                props.SetAlbumTitle(&HSTRING::from(track.album.as_str()))?;
                updater.Update()?;
            }
            Ok(())
        }
    }
}
