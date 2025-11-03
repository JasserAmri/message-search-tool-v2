from flask import Flask, render_template, request, jsonify, send_from_directory, send_file, Response
from datetime import datetime, timedelta
import os
import json
import sys
import time
import uuid
from functools import wraps
from dotenv import load_dotenv
from search_messages import main as run_search_function
import threading
import queue

app = Flask(__name__)

# Store active searches with their queues
active_searches = {}
search_status = {}

# Determine a writable logs directory (Vercel serverless allows only /tmp)
LOG_DIR = os.environ.get('LOG_DIR')
if not LOG_DIR:
    # Check if running on Vercel
    if os.environ.get('VERCEL') or os.environ.get('NOW_REGION') or os.environ.get('VERCEL_ENV'):
        LOG_DIR = '/tmp/logs'
    else:
        LOG_DIR = 'logs'

# Ensure the logs directory exists
try:
    os.makedirs(LOG_DIR, exist_ok=True)
except Exception as e:
    # As a last resort, fall back to /tmp
    print(f"Failed to create LOG_DIR {LOG_DIR}: {e}")
    LOG_DIR = '/tmp/logs'
    os.makedirs(LOG_DIR, exist_ok=True)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/search/stream/<search_id>')
def search_stream(search_id):
    """Server-Sent Events endpoint for real-time search updates"""
    def generate():
        # Get or create queue for this search
        if search_id not in active_searches:
            yield f"data: {json.dumps({'error': 'Search not found'})}\n\n"
            return
        
        msg_queue = active_searches[search_id]
        
        while True:
            try:
                # Wait for message with timeout
                msg = msg_queue.get(timeout=1)
                
                if msg is None:  # Sentinel value for completion
                    break
                    
                yield f"data: {json.dumps(msg)}\n\n"
                
            except queue.Empty:
                # Send heartbeat to keep connection alive
                yield f": heartbeat\n\n"
                
                # Check if search is done
                if search_id in search_status and search_status[search_id].get('completed'):
                    break
    
    return Response(generate(), mimetype='text/event-stream')

@app.route('/api/search/cancel/<search_id>', methods=['POST'])
def cancel_search(search_id):
    """Cancel an active search"""
    if search_id in search_status:
        search_status[search_id]['cancelled'] = True
        return jsonify({'status': 'cancelled'})
    return jsonify({'error': 'Search not found'}), 404

@app.route('/api/search', methods=['POST'])
def search():
    try:
        data = request.json
        if not data:
            return jsonify({'error': 'Invalid or missing JSON body'}), 400

        search_id = datetime.now().strftime('search_%Y%m%d_%H%M%S')

        # Parse dates
        start_date = datetime.fromisoformat(data.get('start_date'))
        end_date = datetime.fromisoformat(data.get('end_date'))

        # Save search parameters
        export_filename = data.get('export_filename', '').strip()
        params = {
            'keywords': data.get('keywords', []),
            'start_date': start_date.isoformat(),
            'end_date': end_date.isoformat(),
            'chunk_days': data.get('chunk_days', 3),
            'limit_per_chunk': data.get('limit_per_chunk', 20000),
            'export_filename': export_filename,
            'started_at': datetime.now().isoformat()
        }

        # Create a unique ID for this search
        search_id = f"search_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        # Save search parameters to a file
        with open(os.path.join(LOG_DIR, f'{search_id}_params.json'), 'w') as f:
            json.dump(params, f)

        # Run search in background
        def search_task():
            # Create event queue for this search
            msg_queue = queue.Queue(maxsize=100)
            cancel_flag = {'cancelled': False}
            
            active_searches[search_id] = msg_queue
            search_status[search_id] = cancel_flag
            
            try:
                # Ensure logs directory exists
                os.makedirs(LOG_DIR, exist_ok=True)

                # Update environment variables for this search
                os.environ['KEYWORDS'] = ','.join(params['keywords'])
                os.environ['START_DATE'] = params['start_date']
                os.environ['END_DATE'] = params['end_date']
                os.environ['CHUNK_DAYS'] = str(params['chunk_days'])
                os.environ['LIMIT_PER_CHUNK'] = str(params['limit_per_chunk'])
                os.environ['EXPORT_FILENAME'] = params.get('export_filename', '')
                os.environ['AUTO_OPTIMIZE'] = 'true'  # Enable intelligent sampling

                # Write initial log message
                start_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                log_message(f'Search started at {start_time}', search_id)
                log_message(f'Keywords: {params["keywords"]}', search_id)
                log_message(f'Date range: {params["start_date"]} to {params["end_date"]}', search_id)
                log_message('-' * 50, search_id)

                try:
                    # Set up search_messages to use our queue and cancel flag
                    from search_messages import set_event_queue, set_cancel_flag, main as search_main
                    set_event_queue(msg_queue)
                    set_cancel_flag(cancel_flag)
                    
                    # Run the search function
                    search_main()
                finally:
                    # Write completion marker
                    end_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    log_message(f'\nSearch completed at {end_time}', search_id)
                    log_message('=' * 50, search_id)
                    
                    # Mark as completed and send completion signal
                    search_status[search_id]['completed'] = True
                    msg_queue.put(None)  # Sentinel to close SSE stream
                    
            except Exception as e:
                log_message(f"❌ Error during search: {str(e)}", search_id)
                msg_queue.put({'type': 'error', 'message': str(e)})
                msg_queue.put(None)
                raise
            finally:
                # Cleanup after some time
                def cleanup():
                    time.sleep(300)  # Keep for 5 minutes
                    if search_id in active_searches:
                        del active_searches[search_id]
                    if search_id in search_status:
                        del search_status[search_id]
                threading.Thread(target=cleanup, daemon=True).start()

        # Start the search in a separate thread
        from threading import Thread
        thread = Thread(target=search_task)
        thread.daemon = True
        thread.start()

        return jsonify({
            'status': 'started',
            'search_id': search_id,
            'params': params
        })
    except Exception as e:
        import traceback
        # Mask sensitive env values
        masked_env = {k: ('****' if any(x in k.upper() for x in ['PASS', 'TOKEN', 'SECRET']) else v)
                      for k, v in os.environ.items() if k in ['DB_HOST', 'DB_PORT', 'DB_NAME', 'DB_USER', 'DB_SSLMODE'] or 'PASS' in k.upper()}
        print("\n===== API Error (/api/search) =====")
        print(f"Error: {e}")
        print("Traceback:\n" + traceback.format_exc())
        print("Env summary:", masked_env)
        try:
            print("Request JSON:", request.get_json(silent=True))
        except Exception:
            pass
        print("===== End API Error =====\n")
        return jsonify({'error': 'Internal server error', 'details': str(e)}), 500

def log_message(message, search_id=None):
    """Log a message to both console and log file"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_entry = f"{timestamp} - {message}"
    
    # Always print to console
    print(log_entry)
    
    # Write to log file if search_id is provided
    if search_id:
        try:
            # Ensure LOG_DIR exists
            os.makedirs(LOG_DIR, exist_ok=True)
            
            # Try writing to the log file
            log_path = os.path.join(LOG_DIR, f'{search_id}.log')
            with open(log_path, 'a', encoding='utf-8') as f:
                f.write(f"{log_entry}\n")
                
        except Exception as e:
            # If writing to LOG_DIR fails, try /tmp/logs as fallback
            try:
                temp_log_dir = '/tmp/logs'
                os.makedirs(temp_log_dir, exist_ok=True)
                temp_log_path = os.path.join(temp_log_dir, f'{search_id}.log')
                with open(temp_log_path, 'a', encoding='utf-8') as f:
                    f.write(f"{timestamp} - [FALLBACK LOG] {message}\n")
                print(f"Logged to fallback location: {temp_log_path}")
            except Exception as inner_e:
                print(f"Failed to write to log file: {str(inner_e)}")

@app.route('/api/logs/<search_id>')
def get_logs(search_id):
    try:
        # Try multiple possible log locations
        possible_paths = [
            os.path.join(LOG_DIR, f'{search_id}.log'),
            os.path.join('/tmp', 'logs', f'{search_id}.log'),
            os.path.join(os.getcwd(), 'logs', f'{search_id}.log')
        ]
        
        log_content = ""
        log_found = False
        
        for log_path in possible_paths:
            try:
                if os.path.exists(log_path):
                    with open(log_path, 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                        log_content = ''.join(lines[-1000:])  # Last 1000 lines
                        log_found = True
                        break
            except Exception as e:
                print(f"Error reading log file {log_path}: {str(e)}")
                continue
        
        if not log_found:
            # If no log file found, check if search is still running
            param_paths = [
                os.path.join(LOG_DIR, f'{search_id}_params.json'),
                os.path.join('/tmp', 'logs', f'{search_id}_params.json'),
                os.path.join(os.getcwd(), 'logs', f'{search_id}_params.json')
            ]
            
            params_exist = any(os.path.exists(p) for p in param_paths)
            
            if params_exist:
                return "Search is still running or logs were not saved. Please try again in a moment.", 202
            else:
                return "No logs found for this search ID. The search may have completed too long ago.", 404
                
        return log_content if log_content.strip() else "Log file is empty."
        
    except Exception as e:
        return f"Error reading logs: {str(e)}", 500

@app.route('/api/searches')
def list_searches():
    searches = []
    try:
        if not os.path.exists(LOG_DIR):
            os.makedirs(LOG_DIR, exist_ok=True)
            return jsonify(searches)
            
        for filename in os.listdir(LOG_DIR):
            if filename.endswith('_params.json'):
                search_id = filename.replace('_params.json', '')
                try:
                    with open(os.path.join(LOG_DIR, filename), 'r') as f:
                        params = json.load(f)
                    
                    # Check if log file exists and if search completed
                    log_path = os.path.join(LOG_DIR, f'{search_id}.log')
                    completed = False
                    if os.path.exists(log_path):
                        with open(log_path, 'r', encoding='utf-8') as log_f:
                            log_content = log_f.read()
                            completed = 'Search completed' in log_content or 'Results saved to' in log_content
                    
                    # Flatten the structure for frontend
                    searches.append({
                        'id': search_id,
                        'keywords': ', '.join(params.get('keywords', [])),
                        'start_date': params.get('start_date'),
                        'end_date': params.get('end_date'),
                        'chunk_days': params.get('chunk_days'),
                        'limit_per_chunk': params.get('limit_per_chunk'),
                        'started_at': params.get('started_at'),
                        'completed': completed,
                        'exists': os.path.exists(log_path)
                    })
                except Exception as e:
                    print(f"Error loading search {filename}: {e}")
                    continue
    except Exception as e:
        print(f"Error listing searches: {e}")
        return jsonify({"error": "Error listing searches", "details": str(e)}), 500
    
    # Sort by most recent first
    searches.sort(key=lambda x: x['id'], reverse=True)
    return jsonify(searches)

@app.route('/download/<filename>')
def download_file(filename):
    """Download the generated Excel file"""
    import pathlib
    
    # PRIORITY: Downloads folder only
    downloads_path = pathlib.Path.home() / "Downloads" / filename
    
    print(f"Looking for file: {filename}")
    print(f"  Checking Downloads: {downloads_path}")
    
    if downloads_path.exists():
        print(f"  ✅ Found in Downloads")
        return send_file(str(downloads_path), as_attachment=True, download_name=filename)
    
    # File not found
    print(f"  ❌ File not found in Downloads folder")
    return jsonify({'error': f'File not found: {filename}'}), 404

@app.route('/api/test-connection', methods=['GET'])
def test_connection():
    """Test database connection and return status"""
    try:
        import psycopg2
        from search_messages import get_db_config
        
        db_config = get_db_config()
        conn = psycopg2.connect(**db_config)
        cursor = conn.cursor()
        cursor.execute("SELECT 1 as test")
        cursor.fetchone()
        cursor.close()
        conn.close()
        
        return jsonify({
            'status': 'connected',
            'host': db_config['host'],
            'database': db_config['database'],
            'user': db_config['user']
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500

@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_from_directory('static', filename)

@app.route('/favicon.ico')
def favicon():
    return send_from_directory('static', 'favicon.ico', mimetype='image/vnd.microsoft.icon')

if __name__ == '__main__':
    print("=" * 60)
    print("🚀 Message Search Tool - Starting Server")
    print("=" * 60)
    print(f"📂 LOG_DIR: {LOG_DIR}")
    print(f"🌐 Server: http://localhost:5000")
    print(f"📊 Database: {os.getenv('DB_HOST', 'Not configured')}")
    print("=" * 60)
    app.run(debug=True, port=5000)

# Export app for WSGI servers (like Vercel)
application = app

