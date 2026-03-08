use crate::commands::NativeCapabilities;

pub fn capabilities() -> NativeCapabilities {
    NativeCapabilities {
        tray_supported: true,
        menu_supported: true,
        global_shortcuts_supported: true,
        seek_supported: false,
        media_controls_hooked: false,
    }
}
