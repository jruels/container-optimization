import os
import sys
from flask import Flask, jsonify

app = Flask(__name__)

# Get Redis configuration from environment
REDIS_HOST = os.environ.get('REDIS_HOST')
REDIS_PORT = os.environ.get('REDIS_PORT', '6379')

# Validate required environment variables at startup
if not REDIS_HOST:
    print("ERROR: REDIS_HOST environment variable is required", file=sys.stderr)
    print("Please set REDIS_HOST to the hostname of your Redis server", file=sys.stderr)
    sys.exit(1)

import redis

# Create Redis connection
redis_client = redis.Redis(host=REDIS_HOST, port=int(REDIS_PORT), decode_responses=True)

@app.route('/')
def home():
    return jsonify({
        "service": "Python Flask API",
        "status": "running",
        "redis_host": REDIS_HOST
    })

@app.route('/health')
def health():
    try:
        redis_client.ping()
        return jsonify({"status": "healthy", "redis": "connected"}), 200
    except redis.ConnectionError:
        return jsonify({"status": "unhealthy", "redis": "disconnected"}), 503

@app.route('/counter')
def counter():
    try:
        count = redis_client.incr('visit_counter')
        return jsonify({"counter": count})
    except redis.ConnectionError as e:
        return jsonify({"error": str(e)}), 503

if __name__ == '__main__':
    print(f"Starting Flask app, connecting to Redis at {REDIS_HOST}:{REDIS_PORT}")
    app.run(host='0.0.0.0', port=5000)
