from flask import Flask, render_template, request, jsonify, send_from_directory, send_file
from datetime import datetime, timedelta
import os
import json
import sys
import uuid
from functools import wraps
from dotenv import load_dotenv
from search_messages import main as run_search_function

app = Flask(__name__)

# Determine a writable logs directory (Vercel serverless allows only /tmp)
LOG_DIR = os.environ.get('LOG_DIR')
if not LOG_DIR:
    LOG_DIR = '/tmp/logs' if os.environ.get('VERCEL') or os.environ.get('NOW_REGION') else 'logs'

# Ensure the logs directory exists
try:
    os.makedirs(LOG_DIR, exist_ok=True)
except Exception:
    # As a last resort, fall back to current directory logs
    LOG_DIR = 'logs'
    os.makedirs(LOG_DIR, exist_ok=True)

@app.route('/')
def index():
    return render_template('index.html')

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
                    # Run the search function
                    from search_messages import main as search_main
                    search_main()
                finally:
                    # Write completion marker
                    end_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    log_message(f'\nSearch completed at {end_time}', search_id)
                    log_message('=' * 50, search_id)
            except Exception as e:
                log_message(f"❌ Error during search: {str(e)}", search_id)
                raise

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
    
    # Try multiple locations
    locations = [
        pathlib.Path(filename),  # Current directory
        pathlib.Path('logs') / filename,  # Logs directory
        pathlib.Path.home() / "Downloads" / filename,  # User's Downloads folder
    ]
    
    for filepath in locations:
        if filepath.exists():
            return send_file(str(filepath), as_attachment=True, download_name=filename)
    
    # File not found in any location
    return jsonify({'error': f'File not found: {filename}'}), 404

@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_from_directory('static', filename)

@app.route('/favicon.ico')
def favicon():
    return send_from_directory('static', 'favicon.ico', mimetype='image/vnd.microsoft.icon')

if __name__ == '__main__':
    app.run(debug=True, port=5000)
