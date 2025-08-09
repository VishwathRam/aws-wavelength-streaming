from flask import Flask, Response, render_template_string
import cv2
import numpy as np
import socket
import threading
import queue
import time

app = Flask(__name__)

# Global variables
frame_queue = queue.Queue(maxsize=10)
latest_frame = None
processing_active = True

def udp_receiver():
    """Receive UDP packets and reconstruct video frames"""
    global latest_frame, processing_active
    
    # Create UDP socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(('0.0.0.0', 1234))
    sock.settimeout(1.0)
    
    print("UDP receiver started on port 1234")
    
    buffer = b''
    
    while processing_active:
        try:
            data, addr = sock.recvfrom(65536)
            buffer += data
            
            # Try to decode frame from buffer
            if len(buffer) > 1000:  # Minimum reasonable frame size
                try:
                    # Convert buffer to numpy array
                    nparr = np.frombuffer(buffer, np.uint8)
                    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                    
                    if frame is not None:
                        latest_frame = frame
                        buffer = b''  # Clear buffer after successful decode
                        
                        # Add to queue for web streaming
                        if not frame_queue.full():
                            frame_queue.put(frame)
                        
                except Exception as e:
                    # If decode fails, keep accumulating buffer
                    if len(buffer) > 100000:  # Prevent buffer overflow
                        buffer = buffer[-50000:]
                    
        except socket.timeout:
            continue
        except Exception as e:
            print(f"UDP receiver error: {e}")
            time.sleep(1)

def generate_frames():
    """Generate frames for Flask streaming"""
    global latest_frame
    
    while True:
        if latest_frame is not None:
            try:
                # Encode frame as JPEG
                ret, buffer = cv2.imencode('.jpg', latest_frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                if ret:
                    frame_bytes = buffer.tobytes()
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
            except Exception as e:
                print(f"Frame generation error: {e}")
        
        time.sleep(0.033)  # ~30 FPS

@app.route('/')
def index():
    """Main page with video stream"""
    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Live Video Stream</title>
        <style>
            body { font-family: Arial, sans-serif; text-align: center; margin: 50px; }
            img { border: 2px solid #333; max-width: 90%; height: auto; }
        </style>
    </head>
    <body>
        <h1>Live Video Stream</h1>
        <img src="{{ url_for('video_feed') }}" alt="Live Stream">
        <p>Streaming from UDP port 1234</p>
    </body>
    </html>
    ''')

@app.route('/video_feed')
def video_feed():
    """Video streaming route"""
    return Response(generate_frames(), 
                   mimetype='multipart/x-mixed-replace; boundary=frame')

if __name__ == '__main__':
    # Start UDP receiver thread
    udp_thread = threading.Thread(target=udp_receiver, daemon=True)
    udp_thread.start()
    
    print("Starting Flask server on port 5000")
    print("UDP receiver listening on port 1234")
    
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)