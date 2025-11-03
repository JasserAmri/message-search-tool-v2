from flask import Flask, render_template, request, jsonify, send_from_directory
from datetime import datetime, timedelta
import os
import json
import sys
import uuid
from functools import wraps
from dotenv import load_dotenv
from search_messages import main as run_search_function

app = Flask(__name__)

# Ensure the logs directory exists
os.makedirs('logs', exist_ok=True)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/search', methods=['POST'])
def search():
    data = request.json
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
    with open(f'logs/{search_id}_params.json', 'w') as f:
        json.dump(params, f)
    
    # Run search in background
    def search_task():
        log_file = None
        try:
            # Ensure logs directory exists
            os.makedirs('logs', exist_ok=True)
            
            # Update environment variables for this search
            os.environ['KEYWORDS'] = ','.join(params['keywords'])
            os.environ['START_DATE'] = params['start_date']
            os.environ['END_DATE'] = params['end_date']
            os.environ['CHUNK_DAYS'] = str(params['chunk_days'])
            os.environ['LIMIT_PER_CHUNK'] = str(params['limit_per_chunk'])
            os.environ['EXPORT_FILENAME'] = params.get('export_filename', '')
            os.environ['AUTO_OPTIMIZE'] = 'true'  # Enable intelligent sampling
            
            # Open log file and redirect stdout/stderr
            log_file = open(f'logs/{search_id}.log', 'a', encoding='utf-8')
            sys.stdout = log_file
            sys.stderr = log_file
            
            # Write initial log message
            start_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            log_message(f'Search started at {start_time}')
            log_message(f'Keywords: {params["keywords"]}')
            log_message(f'Date range: {params["start_date"]} to {params["end_date"]}')
            log_message('-' * 50)
            
            try:
                # Run the search function
                from search_messages import main as search_main
                search_main()
            finally:
                # Restore stdout and stderr
                if log_file:
                    try:
                        end_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        log_message(f'\nSearch completed at {end_time}')
                        log_message('=' * 50)
                        
                        sys.stdout = sys.__stdout__
                        sys.stderr = sys.__stderr__
                        log_file.close()
                    except:
                        # If anything goes wrong, just make sure we don't crash
                        if 'sys' in globals() and hasattr(sys, '__stdout__'):
                            sys.stdout = sys.__stdout__
                            sys.stderr = sys.__stderr__
                        if log_file and not log_file.closed:
                            log_file.close()
        except Exception as e:
            log_message(f"❌ Error during search: {str(e)}")
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

def log_message(message, search_id=None):
    """Log a message to both console and log file"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_entry = f"{timestamp} - {message}"
    
    # Always print to console
    print(log_entry)
    
    # Write to log file if search_id is provided
    if search_id:
        os.makedirs('logs', exist_ok=True)
        with open(f'logs/{search_id}.log', 'a', encoding='utf-8') as f:
            f.write(f"{log_entry}\n")

@app.route('/api/logs/<search_id>')
def get_logs(search_id):
    log_path = os.path.join('logs', f'{search_id}.log')
    try:
        if not os.path.exists(log_path):
            return "No logs found for this search yet. The search might still be running.", 202
        
        # Read the last 1000 lines to avoid sending too much data
        with open(log_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            
        # Return the last 1000 lines (or all if fewer)
        return ''.join(lines[-1000:]) if lines else "No log entries found."
        
    except Exception as e:
        return f"Error reading logs: {str(e)}", 500

@app.route('/api/searches')
def list_searches():
    searches = []
    try:
        if not os.path.exists('logs'):
            os.makedirs('logs', exist_ok=True)
            return jsonify(searches)
            
        for filename in os.listdir('logs'):
            if filename.endswith('_params.json'):
                search_id = filename.replace('_params.json', '')
                try:
                    with open(os.path.join('logs', filename), 'r') as f:
                        params = json.load(f)
                    
                    # Check if log file exists and if search completed
                    log_path = os.path.join('logs', f'{search_id}.log')
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
