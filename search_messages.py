#!/usr/bin/env python3
"""
Message Keyword Search - QuickText msg_message table
Optimized for large datasets with adaptive chunking and performance monitoring.
"""

import os
import sys
import time
import random
import statistics
from datetime import datetime, timedelta
from typing import List, Tuple, Dict
import psycopg2
from psycopg2.extras import RealDictCursor
from openpyxl import Workbook
from dotenv import load_dotenv
from tqdm import tqdm

# Load environment variables
load_dotenv()

# Debug flag
DEBUG = os.getenv('DEBUG', 'false').lower() == 'true'

# Constants that don't change
COLUMNS = ['id', 'created_at', 'content', 'conversation_id', 'trigger', 'user_id']
CHUNK_DAYS_MIN = 1
CHUNK_DAYS_MAX = 7
TIMEOUT_WARNING = 30
MAX_RETRIES = 3
MIN_RESULTS_FOR_CHUNK = 1000

# Global variable to store logs
_logs = []
_event_queue = None  # For SSE streaming
_cancel_flag = {'cancelled': False}  # For cancellation

def set_event_queue(queue):
    """Set the event queue for SSE streaming"""
    global _event_queue
    _event_queue = queue

def set_cancel_flag(flag_dict):
    """Set the cancellation flag dictionary"""
    global _cancel_flag
    _cancel_flag = flag_dict

def is_cancelled():
    """Check if search has been cancelled"""
    return _cancel_flag.get('cancelled', False)

def get_logs():
    """Get all logs captured so far"""
    return "\n".join(_logs)

def log_message(message, progress_data=None):
    """Print a message with timestamp, store it in logs, and emit to SSE queue"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_entry = f"{timestamp} - {message}"
    print(log_entry, flush=True)
    _logs.append(log_entry)
    
    # Send to SSE queue if available
    if _event_queue is not None:
        event = {
            'type': 'log',
            'message': message,
            'timestamp': timestamp
        }
        if progress_data:
            event.update(progress_data)
        try:
            _event_queue.put_nowait(event)
        except:
            pass  # Queue full or closed, continue anyway

def get_db_config():
    """Get database configuration from environment"""
    return {
        'host': os.getenv('DB_HOST'),
        'port': os.getenv('DB_PORT', 5432),
        'database': os.getenv('DB_NAME'),
        'user': os.getenv('DB_USER'),
        'password': os.getenv('DB_PASSWORD'),
        'sslmode': os.getenv('DB_SSLMODE', 'require'),
        'connect_timeout': 10
    }

def validate_config():
    """Check required environment variables"""
    required = ['DB_HOST', 'DB_NAME', 'DB_USER', 'DB_PASSWORD']
    missing = [key for key in required if not os.getenv(key)]
    
    if missing:
        log_message(f"❌ Missing required environment variables: {', '.join(missing)}")
        log_message("   Create .env file from .env.example and configure your database credentials")
        sys.exit(1)

def build_keyword_regex(keywords: List[str]) -> str:
    """Build PostgreSQL regex pattern from keyword list"""
    escaped = [kw.replace('\\', '\\\\').replace('.', '\\.') for kw in keywords]
    return '|'.join(escaped)

def build_where_condition(keywords: List[str]) -> Tuple[str, List]:
    """Build WHERE condition with ILIKE for better performance than regex"""
    conditions = []
    params = []
    
    # Date range condition
    conditions.append("created_at BETWEEN %s AND %s")
    
    # Keyword conditions (OR'ed together)
    keyword_conditions = []
    for keyword in keywords:
        keyword_conditions.append("content ILIKE %s")
        params.append(f'%{keyword}%')
    
    conditions.append(f"({' OR '.join(keyword_conditions)})")
    
    # Fixed conditions
    conditions.extend([
        "trigger = 2",
        "deleted_at IS NULL"
    ])
    
    return " AND ".join(conditions), params

def search_chunk(cursor, keywords: List[str], start_date: datetime, 
                end_date: datetime, limit_per_chunk: int) -> Tuple[list, float]:
    """
    Search one time chunk with optimized query and retry logic
    Returns: (results, duration_in_seconds)
    """
    col_list = ', '.join(COLUMNS)
    where_cond, where_params = build_where_condition(keywords)
    
    query = f"""
        SELECT {col_list}
        FROM msg_message
        WHERE {where_cond}
        LIMIT %s
    """
    
    params = [start_date, end_date] + where_params + [limit_per_chunk]
    
    start_time = time.time()
    try:
        # Log the query being executed
        log_message(f"🔍 Executing query for chunk: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')} ({(end_date - start_date).days} days)")
        log_message(f"   📝 SQL Query:")
        log_message(f"      {query.strip()}")
        log_message(f"   📊 Parameters: start={start_date.strftime('%Y-%m-%d')}, end={end_date.strftime('%Y-%m-%d')}, keywords={keywords}, limit={limit_per_chunk}")
        
        # Execute the query and measure time
        cursor.execute(query, params)
        results = cursor.fetchall()
        query_time = time.time() - start_time
        
        # Log query performance with detailed results
        log_message(f"✅ Query completed in {query_time:.2f} seconds")
        log_message(f"   📈 Results: Found {len(results):,} messages")
        
        if len(results) > 0:
            log_message(f"   📅 Date range of results: {results[0]['created_at']} to {results[-1]['created_at']}")
            # Show sample of first few results
            sample_size = min(3, len(results))
            log_message(f"   📝 Sample results (first {sample_size}):")
            for i in range(sample_size):
                content_preview = results[i]['content'][:100] + '...' if len(results[i]['content']) > 100 else results[i]['content']
                log_message(f"      • ID {results[i]['id']}: {content_preview}")
        
        # If we got results but fewer than threshold, suggest increasing chunk size
        if 0 < len(results) < MIN_RESULTS_FOR_CHUNK:
            return results, -1  # Negative duration signals to increase chunk size
            
        return results, query_time
        
    except Exception as e:
        query_time = time.time() - start_time
        log_message(f"❌ Query failed after {query_time:.2f} seconds: {str(e)}")
        raise
            
def export_to_excel(results: List[dict], output_file: str):
    """Export results to Excel file"""
    log_message(f"\n📊 Exporting results to Excel...")
    log_message(f"   Output file: {output_file}")
    log_message(f"   Total rows: {len(results)}")
    
    wb = Workbook()
    ws = wb.active
    ws.title = "Search Results"
    
    # Write header
    ws.append(COLUMNS)
    
    # Write data
    for row in results:
        ws.append([row.get(col) for col in COLUMNS])
    
    # Auto-adjust column widths
    for column in ws.columns:
        max_length = 0
        column_letter = column[0].column_letter
        for cell in column:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except:
                pass
        adjusted_width = min(max_length + 2, 50)
        ws.column_dimensions[column_letter].width = adjusted_width
    
    log_message(f"   Saving workbook...")
    wb.save(output_file)
    log_message(f"   ✅ Excel file saved successfully: {output_file}")

def is_weekend(date: datetime) -> bool:
    """Check if date falls on weekend (Saturday=5, Sunday=6)"""
    return date.weekday() >= 5

def calculate_memory_based_limit(estimated_avg_row_size: int = 1200) -> int:
    """Calculate safe row limit based on memory constraints"""
    # Conservative: 100MB per chunk
    available_memory = 100 * 1024 * 1024  # 100MB
    safe_limit = available_memory // estimated_avg_row_size
    
    # Clamp between 5k and 50k
    return max(5000, min(50000, safe_limit))

def sample_single_point(cursor, keywords: List[str], sample_date: datetime) -> Tuple[int, float]:
    """Sample a single day and return (count, query_time)"""
    sample_end = sample_date + timedelta(days=1)
    
    where_cond, where_params = build_where_condition(keywords)
    sample_query = f"""
        SELECT COUNT(*) as total
        FROM msg_message
        WHERE {where_cond}
    """
    
    params = [sample_date, sample_end] + where_params
    
    start_time = time.time()
    cursor.execute(sample_query, params)
    result = cursor.fetchone()
    query_time = time.time() - start_time
    
    return result['total'], query_time

def build_adaptive_density_map(samples: List[Dict], start_date: datetime, end_date: datetime, 
                               mean_density: float, limit_per_chunk: int) -> List[Dict]:
    """Build adaptive chunk plan based on sampling results"""
    density_map = []
    current_date = start_date
    
    # Calculate optimal chunk size based on density
    def get_chunk_days(estimated_daily_count: float, is_weekend: bool) -> int:
        if is_weekend:
            # Weekends typically have less traffic - use larger chunks
            base_multiplier = 2.0
        else:
            base_multiplier = 1.0
            
        if estimated_daily_count < 100:
            return int(7 * base_multiplier)  # Very sparse - large chunks
        elif estimated_daily_count < 1000:
            return int(5 * base_multiplier)  # Low density
        elif estimated_daily_count < 5000:
            return int(3 * base_multiplier)  # Medium density
        elif estimated_daily_count < 10000:
            return int(2 * base_multiplier)  # High density
        else:
            return 1  # Very high density - single days
    
    while current_date < end_date:
        # Use mean density as estimate (in real implementation, interpolate from samples)
        estimated_count = mean_density
        weekend = is_weekend(current_date)
        chunk_days = get_chunk_days(estimated_count, weekend)
        
        chunk_end = min(current_date + timedelta(days=chunk_days), end_date)
        estimated_chunk_total = estimated_count * (chunk_end - current_date).days
        
        density_map.append({
            'start': current_date,
            'end': chunk_end,
            'days': (chunk_end - current_date).days,
            'estimated_rows': int(estimated_chunk_total),
            'is_weekend': weekend
        })
        
        current_date = chunk_end
    
    return density_map

def sample_and_optimize(cursor, keywords: List[str], start_date: datetime, end_date: datetime) -> Tuple[int, int, List[Dict]]:
    """
    Enhanced multi-point sampling with statistical analysis
    Returns: (optimal_chunk_days, optimal_limit, density_map)
    """
    log_message("\n🔬 Running enhanced multi-point statistical sampling...")
    
    total_days = (end_date - start_date).days
    
    # Generate 5-7 sample points
    sample_points = []
    if total_days >= 7:
        # Multiple sample points for statistical significance
        sample_points = [
            start_date + timedelta(days=2),                    # Early
            start_date + timedelta(days=total_days // 4),      # 25%
            start_date + timedelta(days=total_days // 2),      # 50% (middle)
            start_date + timedelta(days=3 * total_days // 4),  # 75%
            end_date - timedelta(days=2),                      # Late
        ]
        
        # Add 1-2 random points for anomaly detection
        if total_days > 14:
            random_days = random.sample(range(3, total_days - 3), min(2, total_days - 6))
            sample_points.extend([start_date + timedelta(days=d) for d in random_days])
    else:
        # For short ranges, sample what we can
        sample_points = [start_date + timedelta(days=i) for i in range(0, total_days, max(1, total_days // 3))]
    
    # Sample each point
    samples = []
    log_message(f"   Sampling {len(sample_points)} strategic points across date range...")
    
    for i, sample_date in enumerate(sample_points, 1):
        try:
            count, query_time = sample_single_point(cursor, keywords, sample_date)
            weekend = is_weekend(sample_date)
            
            samples.append({
                'date': sample_date,
                'count': count,
                'query_time': query_time,
                'is_weekend': weekend
            })
            
            weekend_label = " (weekend)" if weekend else ""
            log_message(f"   📊 Sample {i}/{len(sample_points)}: {sample_date.strftime('%Y-%m-%d')}{weekend_label} = {count:,} messages ({query_time:.2f}s)")
            
        except Exception as e:
            log_message(f"   ⚠️  Sample {i} failed: {e}")
            continue
    
    if not samples:
        log_message(f"   ⚠️  All sampling failed, using defaults")
        return 3, 20000, []
    
    # Statistical analysis
    counts = [s['count'] for s in samples]
    mean_density = statistics.mean(counts)
    
    if len(counts) > 1:
        std_dev = statistics.stdev(counts)
        variance = std_dev / mean_density if mean_density > 0 else 0
    else:
        std_dev = 0
        variance = 0
    
    # Weekday vs weekend analysis
    weekday_samples = [s['count'] for s in samples if not s['is_weekend']]
    weekend_samples = [s['count'] for s in samples if s['is_weekend']]
    
    weekday_avg = statistics.mean(weekday_samples) if weekday_samples else mean_density
    weekend_avg = statistics.mean(weekend_samples) if weekend_samples else mean_density
    weekend_penalty = ((weekday_avg - weekend_avg) / weekday_avg * 100) if weekday_avg > 0 else 0
    
    log_message(f"\n   📈 Statistical Analysis:")
    log_message(f"      Mean density: {mean_density:,.1f} messages/day")
    log_message(f"      Std deviation: {std_dev:,.1f}")
    log_message(f"      Variance coefficient: {variance:.2f}")
    
    if weekday_samples and weekend_samples:
        log_message(f"      Weekday average: {weekday_avg:,.0f} messages/day")
        log_message(f"      Weekend average: {weekend_avg:,.0f} messages/day")
        log_message(f"      Weekend penalty: {weekend_penalty:.0f}% fewer messages")
    
    # Calculate memory-based limit
    optimal_limit = calculate_memory_based_limit()
    log_message(f"\n   💾 Memory-based limit: {optimal_limit:,} rows per chunk")
    
    # Build adaptive density map
    log_message(f"\n   🗺️  Building adaptive density map...")
    density_map = build_adaptive_density_map(samples, start_date, end_date, mean_density, optimal_limit)
    
    # Log density map summary
    total_chunks = len(density_map)
    avg_chunk_days = statistics.mean([c['days'] for c in density_map])
    
    log_message(f"      Total chunks planned: {total_chunks}")
    log_message(f"      Average chunk size: {avg_chunk_days:.1f} days")
    log_message(f"      Chunk size range: {min(c['days'] for c in density_map)}-{max(c['days'] for c in density_map)} days")
    
    # Show first few chunks as preview
    log_message(f"\n   📋 Chunk Plan Preview (first 5):")
    for i, chunk in enumerate(density_map[:5], 1):
        weekend_label = " 🏖️" if chunk['is_weekend'] else ""
        log_message(f"      Chunk {i}: {chunk['start'].strftime('%Y-%m-%d')} to {chunk['end'].strftime('%Y-%m-%d')} "
                   f"({chunk['days']}d{weekend_label}) ~ {chunk['estimated_rows']:,} rows")
    
    if total_chunks > 5:
        log_message(f"      ... and {total_chunks - 5} more chunks")
    
    # Estimate total time
    avg_query_time = statistics.mean([s['query_time'] for s in samples])
    estimated_time = avg_query_time * total_chunks
    estimated_total = sum(c['estimated_rows'] for c in density_map)
    
    log_message(f"\n   ⏱️  Performance Estimates:")
    log_message(f"      Estimated total results: ~{estimated_total:,}")
    log_message(f"      Estimated total time: ~{estimated_time:.0f}s ({estimated_time/60:.1f} min)")
    log_message(f"      Average query time: {avg_query_time:.2f}s")
    
    # Return a default chunk size for legacy compatibility (will use density_map instead)
    optimal_chunk = int(avg_chunk_days)
    
    return optimal_chunk, optimal_limit, density_map

def main():
    """Main execution with adaptive chunking"""
    # Read configuration from environment (fresh for each run)
    keywords = [k.strip() for k in os.getenv('KEYWORDS', 'smoke,smoking').split(',') if k.strip()]
    start_date = datetime.fromisoformat(os.getenv('START_DATE', (datetime.now() - timedelta(days=30)).isoformat()))
    end_date = datetime.fromisoformat(os.getenv('END_DATE', datetime.now().isoformat()))
    chunk_days_start = int(os.getenv('CHUNK_DAYS', '3'))
    limit_per_chunk = int(os.getenv('LIMIT_PER_CHUNK', '20000'))
    custom_filename = os.getenv('EXPORT_FILENAME', '').strip()
    auto_optimize = os.getenv('AUTO_OPTIMIZE', 'true').lower() == 'true'
    
    log_message("=" * 60)
    log_message("Message Keyword Search Tool - Optimized")
    log_message("=" * 60)
    log_message("📋 Search Configuration:")
    log_message(f"   Keywords: {', '.join(keywords)}")
    log_message(f"   Date range: {start_date.strftime('%Y-%m-%d %H:%M:%S')} to {end_date.strftime('%Y-%m-%d %H:%M:%S')}")
    log_message(f"   Initial chunk size: {chunk_days_start} days (min: {CHUNK_DAYS_MIN}, max: {CHUNK_DAYS_MAX})")
    log_message(f"   Initial max results per chunk: {limit_per_chunk:,}")
    log_message(f"   Auto-optimization: {'Enabled' if auto_optimize else 'Disabled'}")
    log_message("-" * 60)
    log_message("\n🔍 Starting search...")
    log_message(f"   Search method: ILIKE (case-insensitive)")
    log_message(f"   Keywords: {', '.join(keywords)}")
    log_message("-" * 30)
    
    # Validate configuration
    validate_config()
    
    # Connect to database
    db_config = get_db_config()
    log_message("\n🔌 Attempting database connection...")
    log_message(f"   Host: {db_config['host']}")
    log_message(f"   Port: {db_config['port']}")
    log_message(f"   Database: {db_config['database']}")
    log_message(f"   User: {db_config['user']}")
    log_message(f"   SSL Mode: {db_config.get('sslmode', 'prefer')}")
    
    try:
        import socket
        # Test DNS resolution
        try:
            socket.gethostbyname(db_config['host'])
            log_message(f"   ✅ DNS resolution successful")
        except socket.gaierror as e:
            log_message(f"   ❌ DNS resolution failed: {e}")
            log_message(f"   → Check internet connection or hostname")
            return
        
        # Test connection with timeout
        log_message(f"   Connecting with {db_config.get('connect_timeout', 10)}s timeout...")
        conn = psycopg2.connect(**db_config, cursor_factory=RealDictCursor)
        log_message("   ✅ Database connected successfully")
        
        # Test query to verify permissions
        try:
            with conn.cursor() as test_cursor:
                test_cursor.execute("SELECT 1 as test")
                test_cursor.fetchone()
            log_message("   ✅ Database permissions verified")
        except Exception as e:
            log_message(f"   ⚠️  Database connected but query failed: {e}")
            
    except psycopg2.OperationalError as e:
        error_msg = str(e).lower()
        log_message(f"❌ Database connection failed: {e}")
        
        if 'password' in error_msg or 'authentication' in error_msg:
            log_message("   → Cause: Invalid credentials (wrong password or username)")
            log_message("   → Solution: Check DB_USER and DB_PASSWORD in .env file")
        elif 'timeout' in error_msg or 'timed out' in error_msg:
            log_message("   → Cause: Connection timeout")
            log_message("   → Solution: Check internet connection or firewall settings")
        elif 'could not connect' in error_msg or 'connection refused' in error_msg:
            log_message("   → Cause: Cannot reach database server")
            log_message("   → Solution: Check DB_HOST, DB_PORT, and network connectivity")
        elif 'ssl' in error_msg:
            log_message("   → Cause: SSL/TLS connection issue")
            log_message("   → Solution: Check DB_SSLMODE setting or SSL certificates")
        elif 'no such host' in error_msg or 'name or service not known' in error_msg:
            log_message("   → Cause: Cannot resolve hostname")
            log_message("   → Solution: Check DB_HOST value and DNS settings")
        else:
            log_message("   → Cause: Unknown operational error")
            log_message("   → Solution: Check all database configuration in .env file")
        return
        
    except psycopg2.Error as e:
        log_message(f"❌ Database error: {e}")
        log_message(f"   → Error code: {e.pgcode if hasattr(e, 'pgcode') else 'N/A'}")
        log_message(f"   → Solution: Check database configuration and permissions")
        return
        
    except Exception as e:
        log_message(f"❌ Unexpected error connecting to database: {e}")
        log_message(f"   → Type: {type(e).__name__}")
        return
    
    # Run intelligent sampling if auto-optimize is enabled
    density_map = []
    if auto_optimize:
        with conn.cursor() as cursor:
            chunk_days_start, limit_per_chunk, density_map = sample_and_optimize(cursor, keywords, start_date, end_date)
            log_message(f"\n✅ Optimization complete - using adaptive chunking with {limit_per_chunk:,} limit per chunk")
    
    # Initialize variables for adaptive chunking
    current_date = start_date
    chunk_days = chunk_days_start
    all_results = []
    total_chunks = 0
    total_time = 0
    
    try:
        # Process in chunks
        total_days = (end_date - start_date).days
        
        # Use density map if available, otherwise use traditional chunking
        if density_map:
            log_message(f"\n🗺️  Using adaptive density map with {len(density_map)} pre-planned chunks")
            estimated_chunks = len(density_map)
            chunk_plan = density_map
        else:
            log_message(f"Processing {total_days} days in chunks of {chunk_days} days...")
            estimated_chunks = (total_days + chunk_days - 1) // chunk_days
            chunk_plan = None
        
        # Disable tqdm when running in web mode to avoid progress bar artifacts in logs
        use_tqdm = sys.stdout.isatty()
        
        pbar = tqdm(total=total_days, desc="Progress", disable=not use_tqdm)
        
        try:
            # Iterate through planned chunks or traditional chunks
            if chunk_plan:
                # Use adaptive density map
                for chunk_info in chunk_plan:
                    # Check for cancellation
                    if is_cancelled():
                        log_message("\n⚠️  Search cancelled by user")
                        break
                    
                    total_chunks += 1
                    current_date = chunk_info['start']
                    chunk_end = chunk_info['end']
                    chunk_days_actual = chunk_info['days']
                    
                    # Calculate progress
                    days_processed = (current_date - start_date).days
                    progress_percent = int((total_chunks / estimated_chunks) * 100)
                    
                    # Estimate time remaining
                    if total_time > 0 and total_chunks > 1:
                        avg_time_per_chunk = total_time / (total_chunks - 1)
                        chunks_remaining = estimated_chunks - total_chunks
                        eta_seconds = int(avg_time_per_chunk * chunks_remaining)
                        eta_minutes = eta_seconds // 60
                        eta_display = f"{eta_minutes}m {eta_seconds % 60}s" if eta_minutes > 0 else f"{eta_seconds}s"
                    else:
                        eta_display = "calculating..."
                    
                    # Log chunk info with progress
                    weekend_label = " 🏖️" if chunk_info['is_weekend'] else ""
                    progress_data = {
                        'progress': progress_percent,
                        'current_chunk': total_chunks,
                        'estimated_chunks': estimated_chunks,
                        'eta': eta_display,
                        'results_so_far': len(all_results)
                    }
                    log_message(
                        f"\n📅 Chunk {total_chunks}/{estimated_chunks} ({progress_percent}%) - ETA: {eta_display}\n"
                        f"   Date range: {current_date.strftime('%Y-%m-%d')} to {chunk_end.strftime('%Y-%m-%d')} ({chunk_days_actual} days{weekend_label})\n"
                        f"   Results so far: {len(all_results):,}",
                        progress_data=progress_data
                    )
                    
                    # Execute search with a new cursor for each chunk
                    with conn.cursor() as cursor:
                        chunk_results, duration = search_chunk(
                            cursor, keywords, current_date, chunk_end, limit_per_chunk
                        )
                        total_time += duration if duration > 0 else 0
                        
                        # Process results
                        all_results.extend(chunk_results)
                        pbar.update(chunk_days_actual)
                        
                        # Check if hit limit
                        if len(chunk_results) >= limit_per_chunk:
                            log_message(f"\n⚠️  Hit limit of {limit_per_chunk} results in one chunk")
                            log_message(f"   → Some results may be missing from {current_date.date()}")
            else:
                # Traditional chunking (legacy)
                while current_date < end_date:
                    # Check for cancellation
                    if is_cancelled():
                        log_message("\n⚠️  Search cancelled by user")
                        break
                    
                    total_chunks += 1
                    chunk_end = min(current_date + timedelta(days=chunk_days), end_date)
                    
                    # Calculate progress
                    # Calculate progress
                    days_processed = (current_date - start_date).days
                    progress_percent = int((days_processed / total_days) * 100) if total_days > 0 else 0
                    
                    # Estimate time remaining
                    if total_time > 0 and days_processed > 0:
                        avg_time_per_day = total_time / days_processed
                        days_remaining = total_days - days_processed
                        eta_seconds = int(avg_time_per_day * days_remaining)
                        eta_minutes = eta_seconds // 60
                        eta_display = f"{eta_minutes}m {eta_seconds % 60}s" if eta_minutes > 0 else f"{eta_seconds}s"
                    else:
                        eta_display = "calculating..."
                    
                    # Log chunk info with progress
                    chunk_days_actual = (chunk_end - current_date).days
                    progress_data = {
                        'progress': progress_percent,
                        'current_chunk': total_chunks,
                        'estimated_chunks': estimated_chunks,
                        'eta': eta_display,
                        'results_so_far': len(all_results)
                    }
                    log_message(
                        f"\n📅 Chunk {total_chunks}/{estimated_chunks} ({progress_percent}%) - ETA: {eta_display}\n"
                        f"   Date range: {current_date.strftime('%Y-%m-%d')} to {chunk_end.strftime('%Y-%m-%d')} ({chunk_days_actual} days)\n"
                        f"   Results so far: {len(all_results):,}",
                        progress_data=progress_data
                    )
                    
                    # Skip chunks that are completely before start_date (shouldn't happen but just in case)
                    if chunk_end <= start_date:
                        log_message(f"Skipping chunk (before start date)")
                        current_date = chunk_end
                        pbar.update(chunk_days_actual)
                        continue
                    
                    # Execute search with a new cursor for each chunk
                    with conn.cursor() as cursor:
                        chunk_results, duration = search_chunk(
                            cursor, keywords, current_date, chunk_end, limit_per_chunk
                        )
                        total_time += duration if duration > 0 else 0
                        
                        # Process results
                        all_results.extend(chunk_results)
                        pbar.update((chunk_end - current_date).days)
                        
                        # Performance feedback
                        if duration > TIMEOUT_WARNING:
                            log_message(f"\n⚠️  Slow query: {duration:.1f}s (chunk {chunk_days}d)")
                            chunk_days = max(CHUNK_DAYS_MIN, chunk_days - 1)
                            log_message(f"   → Reducing chunk size to {chunk_days} days")
                        elif duration > 0 and duration < 30 and chunk_days < CHUNK_DAYS_MAX:
                            chunk_days = min(CHUNK_DAYS_MAX, chunk_days + 1)
                            log_message(f"\n✓ Fast query: {duration:.1f}s")
                            log_message(f"   → Increasing chunk size to {chunk_days} days")
                        
                        # Check if hit limit
                        if len(chunk_results) >= limit_per_chunk:
                            log_message(f"\n⚠️  Hit limit of {limit_per_chunk} results in one chunk")
                            log_message(f"   → Some results may be missing from {current_date.date()}")
                        
                        current_date = chunk_end
            
            # Process results if we have any
            if all_results:
                # Generate a filename for reference
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                if custom_filename:
                    safe_filename = "".join(c for c in custom_filename if c.isalnum() or c in (' ', '-', '_')).strip()
                    filename = f'{safe_filename}.xlsx' if not safe_filename.endswith('.xlsx') else safe_filename
                else:
                    filename = f'keyword_results_{timestamp}.xlsx'
                
                # ALWAYS save to Downloads folder - no fallbacks
                downloads_path = os.path.join(os.path.expanduser('~'), 'Downloads', filename)
                
                log_message(f"\n💾 Saving to Downloads folder: {downloads_path}")
                
                # Export to Excel
                export_to_excel(all_results, downloads_path)
                
                # Print summary
                log_message("\n" + "=" * 60)
                log_message(f"✅ Search completed successfully!")
                log_message(f"   Total results: {len(all_results):,}")
                log_message(f"   Total chunks: {total_chunks}")
                log_message(f"   Total time: {total_time:.1f} seconds")
                log_message(f"   📁 File saved to: {downloads_path}")
                log_message("=" * 60)
                
                # Return the results and file path for the web app to handle
                return {
                    'success': True,
                    'result_count': len(all_results),
                    'excel_path': output_path,
                    'filename': filename,
                    'logs': get_logs()
                }
            else:
                log_message("\nNo results found for the given criteria.")
                return {
                    'success': True,
                    'result_count': 0,
                    'message': 'No results found',
                    'logs': get_logs()
                }
        finally:
            pbar.close()
                
    except Exception as e:
        log_message(f"\n❌ An error occurred during search: {e}")
        if 'conn' in locals() and conn is not None:
            conn.rollback()
        return {
            'success': False,
            'error': str(e),
            'logs': get_logs()
        }
    finally:
        # Close database connection
        if 'conn' in locals() and conn is not None:
            conn.close()
            log_message("✅ Database connection closed")

if __name__ == "__main__":
    main()
