#!/usr/bin/env python3
"""Simple HTTP server for viewing the generated Leaflet maps"""

import http.server
import socketserver
import os
import webbrowser
import argparse
from pathlib import Path

def serve(html_file: str, port: int = 8000):
    """Serve the HTML map on a local HTTP server."""
    html_path = Path(html_file).absolute()
    if not html_path.exists():
        print(f"Error: {html_file} not found")
        return

    os.chdir(html_path.parent)

    Handler = http.server.SimpleHTTPRequestHandler
    with socketserver.TCPServer(("", port), Handler) as httpd:
        url = f"http://localhost:{port}/{html_path.name}"
        print(f"\n🗺️  Server running at: {url}")
        print(f"Press Ctrl+C to stop\n")

        # Try to open in browser
        try:
            webbrowser.open(url)
        except Exception:
            pass

        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n\n✓ Server stopped")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Serve building polygons map')
    parser.add_argument('--html', default='output/buildings_map.html',
                       help='Path to HTML map file')
    parser.add_argument('--port', type=int, default=8000,
                       help='Port to serve on')
    args = parser.parse_args()

    serve(args.html, args.port)
