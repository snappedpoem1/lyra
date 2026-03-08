use lyra_core::LyraCore;
use std::path::PathBuf;
use std::thread;
use std::time::Duration;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let app_data_dir = PathBuf::from("C:\\Users\\Admin\\AppData\\Roaming\\com.lyra.player");
    let lyra = LyraCore::new(app_data_dir)?;
    
    println!("=== PLAYBACK FUNCTIONALITY TEST ===\n");
    
    println!("Finding a track to play...");
    let tracks = lyra.list_tracks(None, None)?;
    
    if tracks.is_empty() {
        eprintln!("ERROR: No tracks found!");
        return Ok(());
    }
    
    let track = &tracks[0];
    println!("Selected: {} - {}", track.artist, track.title);
    println!("Path: {}", track.path);
    println!("File exists: {}\n", std::path::Path::new(&track.path).exists());
    
    println!("Testing play...");
    match lyra.play_track(track.id) {
        Ok(state) => {
            println!("SUCCESS: Play command successful");
            println!("Status: {}", state.status);
            println!("Duration: {}s\n", state.duration_seconds);
            
            println!("Waiting 3 seconds...");
            thread::sleep(Duration::from_secs(3));
            
            let state = lyra.get_playback_state()?;
            println!("Position: {:.1}s\n", state.position_seconds);
            
            println!("Testing pause...");
            let state = lyra.toggle_playback()?;
            println!("Status: {}\n", state.status);
            
            thread::sleep(Duration::from_secs(1));
            
            println!("Testing resume...");
            let state = lyra.toggle_playback()?;
            println!("Status: {}\n", state.status);
            
            thread::sleep(Duration::from_secs(2));
            
            println!("Testing next track...");
            match lyra.play_next() {
                Ok(state) => {
                    println!("SUCCESS: Next track: {} - {}\n",
                        state.current_track.as_ref().map(|t| t.artist.as_str()).unwrap_or("Unknown"),
                        state.current_track.as_ref().map(|t| t.title.as_str()).unwrap_or("Unknown")
                    );
                }
                Err(e) => println!("WARNING: Next track error: {}\n", e),
            }
            
            thread::sleep(Duration::from_secs(2));
            
            println!("Stopping playback...");
            lyra.toggle_playback()?;
            
            println!("\n=== PLAYBACK TEST COMPLETE ===");
            println!("If you heard audio, playback is working correctly!");
        }
        Err(e) => {
            eprintln!("ERROR: Play failed: {}", e);
        }
    }
    
    Ok(())
}
