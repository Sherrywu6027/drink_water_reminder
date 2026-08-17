import webview
import os
import time
import sys

class Api:
    def record_eye(self, duration):
        """duration: 本次护眼总秒数"""
        eye_dir = os.path.join(os.path.dirname(__file__))
        eye_file = os.path.join(eye_dir, 'eye_autorecord.txt')
        with open(eye_file, 'a', encoding='utf-8') as f:
            f.write(f"{int(time.time())},{duration}\n")
        return "ok"

def main():
    api = Api()
    html_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'index.html'))
    autostart = '--autostart' in sys.argv
    window = webview.create_window('护眼训练', html_path, js_api=api, width=900, height=700)
    if autostart:
        def on_loaded():
            window.evaluate_js('if(window.startTimer) startTimer();')
        webview.start(on_loaded, window)
    else:
        webview.start()

if __name__ == '__main__':
    main() 