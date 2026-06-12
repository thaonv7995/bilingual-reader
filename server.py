#!/usr/bin/env python3
import http.server
import socketserver
import urllib.request
import urllib.error
import json
import sys

PORT = 27099

class ProxyHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        # Set CORS headers for all requests to ensure ease of testing
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def do_POST(self):
        # Intercept proxy completions API to bypass CORS
        if self.path == "/api/chat":
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length == 0:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b'{"error": {"message": "Empty body"}}')
                return

            body = self.rfile.read(content_length)
            
            try:
                data = json.loads(body.decode('utf-8'))
                
                # Extract routing parameters
                base_url = data.get('baseURL', 'https://api.openai.com/v1').rstrip('/')
                target_url = f"{base_url}/chat/completions"
                api_key = data.get('apiKey', '')
                
                # Construct headers for target request
                headers = {
                    'Content-Type': 'application/json',
                    'Accept': 'text/event-stream',
                    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36'
                }
                if api_key:
                    headers['Authorization'] = f'Bearer {api_key}'
                
                # Clean payload (remove baseURL/apiKey so the target LLM endpoint doesn't fail on unknown fields)
                payload = {
                    'model': data.get('model', 'gpt-4o-mini'),
                    'messages': data.get('messages', []),
                    'stream': data.get('stream', False)
                }
                
                print(f"[Proxy] Forwarding request to target: {target_url} (model: {payload['model']})")
                
                req = urllib.request.Request(
                    target_url,
                    data=json.dumps(payload).encode('utf-8'),
                    headers=headers,
                    method='POST'
                )
                
                try:
                    with urllib.request.urlopen(req, timeout=120) as res:
                        self.send_response(200)
                        self.send_header("Content-Type", res.info().get_content_type() or "text/event-stream")
                        self.send_header("Cache-Control", "no-cache")
                        self.send_header("Connection", "keep-alive")
                        self.end_headers()
                        
                        # Stream chunks directly back to the browser line-by-line
                        for line in res:
                            self.wfile.write(line)
                            self.wfile.flush()
                            
                except urllib.error.HTTPError as e:
                    err_body = e.read().decode('utf-8')
                    print(f"[Proxy Error] HTTP {e.code}: {err_body}")
                    self.send_response(e.code)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(err_body.encode('utf-8'))
                except Exception as e:
                    print(f"[Proxy Error] Exception: {str(e)}")
                    self.send_response(500)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    err_msg = json.dumps({"error": {"message": f"Proxy exception: {str(e)}"}} )
                    self.wfile.write(err_msg.encode('utf-8'))
                    
            except Exception as e:
                print(f"[Proxy Error] JSON parse error: {str(e)}")
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                err_msg = json.dumps({"error": {"message": f"Invalid request body: {str(e)}"}} )
                self.wfile.write(err_msg.encode('utf-8'))
        else:
            # Fallback to serving static files
            super().do_POST()

# Configure socket reuse to prevent port-in-use errors on restart
socketserver.TCPServer.allow_reuse_address = True

with socketserver.TCPServer(("", PORT), ProxyHandler) as httpd:
    print(f"Bilingual Reader Server started on port {PORT} (with AI proxy).")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server.")
        sys.exit(0)
