import time
import re
import subprocess
import rumps

from AppKit import NSApplication, NSApplicationActivationPolicyAccessory, NSObject

REMINDER_INTERVAL_SECONDS = 60 * 30
CHECK_INTERVAL_SECONDS = 5


class MainThreadDispatcher(NSObject):
    def runCallback_(self, callback):
        callback()


# Helper function to bounce tasks to the main thread
def run_on_main_thread(callback):
    dispatcher = MainThreadDispatcher.alloc().init()
    dispatcher.performSelectorOnMainThread_withObject_waitUntilDone_(
        "runCallback:",
        callback,
        False # False means asynchronous, won't block the calling thread
    )


class NudgesApp(rumps.App):
    def __init__(self):
        super().__init__(name="Nudges")
        
        self.status_item = rumps.MenuItem("Initializing")
        self.menu = [self.status_item]
        self.busy = True

        self.last_notification_time = time.monotonic()

        self.timer = rumps.Timer(self.check_and_remind, CHECK_INTERVAL_SECONDS)
        self.timer.start()

    def _set_reason_text(self, tooltip_text: str):
        self.status_item.title = tooltip_text

    def _set_busy(self, reason: str):
        self.title = f"🔕"
        self._set_reason_text(f"Notifications disabled: {reason}")
        self.busy = True

    def _set_free(self):
        self.title = "🔔​"
        self._set_reason_text("Notifications enabled")
        self.busy = False

    def _set_error(self, reason: str):
        self.title = f"❌​"
        # Err on the safe side and don't show notifications when status is unknown
        self._set_reason_text(f"Notifications disabled due to error: {reason}")
        self.busy = True

    def _is_zoom_meeting_active(self) -> bool:
        zoom_check = subprocess.run(['pgrep', '-x', 'CptHost'], capture_output=True)
        return zoom_check.returncode == 0

    def _is_screen_sharing_active(self) -> bool:
        pm_check = subprocess.run(['pmset', '-g', 'assertions'], capture_output=True, text=True)
        # Preventing the display from sleeping is a sign of screen sharing (or other
        # video-playing, etc., but that's good enough for now)
        return re.search(r"PreventUserIdleDisplaySleep\s+1", pm_check.stdout) is not None

    def _check_if_busy_and_update_status(self):
        try:
            if self._is_zoom_meeting_active():
                self._set_busy("In a Zoom meeting")
            elif self._is_screen_sharing_active():
                self._set_busy("Screen sharing is active")
            else:
                self._set_free()
        except Exception as e:
            self._set_error(f"Error checking busy status: {e}")

    def alert_with_sound(self, title: str, message: str, **kwargs):
        subprocess.Popen(['afplay', '/System/Library/Sounds/Glass.aiff'])
        rumps.alert(title=title, message=message, **kwargs)

    def check_and_remind(self, _):
        try:
            self._check_if_busy_and_update_status()
            if not self.busy:
                now = time.monotonic()
                if now - self.last_notification_time > REMINDER_INTERVAL_SECONDS:
                    self.last_notification_time = now
                    run_on_main_thread(lambda: self.alert_with_sound(
                        title="Nudge!",
                        message="Double-check your email, calendar, and Slack.",
                        ok="Got it!"
                    ))
        except Exception as e:
            self._set_error(f"Error checking and reminding: {e}")


if __name__ == "__main__":
    ns_app = NSApplication.sharedApplication()
    # Force macOS to recognize this script as a proper UI accessory,
    # so that we can show GUI elements.
    ns_app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    # Allow this application to steal focus from other apps.
    ns_app.activateIgnoringOtherApps_(True)
    # Launch the main notification area app
    NudgesApp().run()