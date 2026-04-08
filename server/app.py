import argparse
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler

class DummyServer(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b"OK")
        
    def do_POST(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b"OK")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=7860)
    args, unknown = parser.parse_known_args()
    
    server = HTTPServer(('0.0.0.0', args.port), DummyServer)
    print(f"Starting dummy server on port {args.port}...")
    server.serve_forever()

if __name__ == '__main__':
    main()