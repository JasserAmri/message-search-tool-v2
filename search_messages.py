#!/usr/bin/env python3
"""
Message Keyword Search - QuickText msg_message table
Optimized for large datasets with adaptive chunking and performance monitoring.
"""

import os
import sys
import time
from datetime import datetime, timedelta
from typing import List, Tuple
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

def log_message(message):
    """Print a message with timestamp"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"{timestamp} - {message}", flush=True)

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
    
    wb.save(output_file)

def sample_and_optimize(cursor, keywords: List[str], start_date: datetime, end_date: datetime) -> Tuple[int, int]:
    """
    Sample the data to determine optimal chunk size and limit
    Returns: (optimal_chunk_days, optimal_limit)
    """
    log_message("\n🔬 Running intelligent sampling to optimize search parameters...")
    
    total_days = (end_date - start_date).days
    
    # Sample 1 day in the middle of the range
    sample_start = start_date + timedelta(days=total_days // 2)
    sample_end = sample_start + timedelta(days=1)
    
    # Build sample query
    where_cond, where_params = build_where_condition(keywords)
    sample_query = f"""
        SELECT COUNT(*) as total
        FROM msg_message
        WHERE {where_cond}
    """
    
    params = [sample_start, sample_end] + where_params
    
    try:
        import time
        start_time = time.time()
        cursor.execute(sample_query, params)
        result = cursor.fetchone()
        sample_time = time.time() - start_time
        sample_count = result['total']
        
        log_message(f"   📊 Sample results (1 day in middle of range):")
        log_message(f"      Date: {sample_start.strftime('%Y-%m-%d')}")
        log_message(f"      Messages found: {sample_count:,}")
        log_message(f"      Query time: {sample_time:.2f}s")
        
        # Determine optimal chunk size based on density
        if sample_count == 0:
            optimal_chunk = 7  # No results, use larger chunks
            optimal_limit = 20000
            log_message(f"   💡 No results in sample - using larger chunks (7 days)")
        elif sample_count < 100:
            optimal_chunk = 7  # Low density, use larger chunks
            optimal_limit = 20000
            log_message(f"   💡 Low density detected - using larger chunks (7 days)")
        elif sample_count < 1000:
            optimal_chunk = 5  # Medium density
            optimal_limit = 20000
            log_message(f"   💡 Medium density detected - using 5-day chunks")
        elif sample_count < 5000:
            optimal_chunk = 3  # High density
            optimal_limit = 20000
            log_message(f"   💡 High density detected - using 3-day chunks")
        else:
            optimal_chunk = 1  # Very high density
            optimal_limit = min(sample_count * 2, 30000)  # Adjust limit based on density
            log_message(f"   💡 Very high density detected - using 1-day chunks")
            log_message(f"   💡 Adjusted limit to {optimal_limit:,} per chunk")
        
        # Estimate total results and time
        estimated_total = sample_count * total_days
        estimated_chunks = (total_days + optimal_chunk - 1) // optimal_chunk
        estimated_time = sample_time * estimated_chunks
        
        log_message(f"   📈 Estimates:")
        log_message(f"      Total results: ~{estimated_total:,}")
        log_message(f"      Chunks needed: ~{estimated_chunks}")
        log_message(f"      Estimated time: ~{estimated_time:.0f}s ({estimated_time/60:.1f} min)")
        
        return optimal_chunk, optimal_limit
        
    except Exception as e:
        log_message(f"   ⚠️  Sampling failed: {e}")
        log_message(f"   Using default parameters")
        return 3, 20000

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
    if auto_optimize:
        with conn.cursor() as cursor:
            chunk_days_start, limit_per_chunk = sample_and_optimize(cursor, keywords, start_date, end_date)
            log_message(f"\n✅ Optimization complete - using {chunk_days_start}-day chunks with {limit_per_chunk:,} limit")
    
    # Initialize variables for adaptive chunking
    current_date = start_date
    chunk_days = chunk_days_start
    all_results = []
    total_chunks = 0
    total_time = 0
    
    try:
        # Process in chunks
        total_days = (end_date - start_date).days
        log_message(f"Processing {total_days} days in chunks of {chunk_days} days...")
        
        # Disable tqdm when running in web mode to avoid progress bar artifacts in logs
        use_tqdm = sys.stdout.isatty()
        
        pbar = tqdm(total=total_days, desc="Progress", disable=not use_tqdm)
        try:
            while current_date < end_date:
                total_chunks += 1
                chunk_end = min(current_date + timedelta(days=chunk_days), end_date)
                
                # Log chunk info
                chunk_days_actual = (chunk_end - current_date).days
                log_message(f"\n📅 Processing chunk {total_chunks}: {current_date.strftime('%Y-%m-%d')} to {chunk_end.strftime('%Y-%m-%d')} ({chunk_days_actual} days)")
                
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
        finally:
            pbar.close()
            
            # Save results to Excel if we have any
            if all_results:
                # Generate filename
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                if custom_filename:
                    # Use custom filename, sanitize it
                    safe_filename = "".join(c for c in custom_filename if c.isalnum() or c in (' ', '-', '_')).strip()
                    filename = f'{safe_filename}_{timestamp}.xlsx'
                else:
                    filename = f'keyword_results_{timestamp}.xlsx'
                
                # Determine save location - try Downloads folder first
                try:
                    import pathlib
                    downloads_path = pathlib.Path.home() / "Downloads"
                    if downloads_path.exists():
                        full_path = downloads_path / filename
                    else:
                        full_path = pathlib.Path(filename)
                except:
                    full_path = pathlib.Path(filename)
                
                # Create workbook and worksheet with UTF-8 encoding
                wb = Workbook()
                ws = wb.active
                ws.title = "Search Results"
                
                # Set encoding options for proper UTF-8 support
                wb.encoding = 'utf-8'
                
                # Write headers with bold formatting
                from openpyxl.styles import Font, Alignment
                header_font = Font(bold=True)
                for col_idx, header in enumerate(COLUMNS, 1):
                    cell = ws.cell(row=1, column=col_idx, value=header)
                    cell.font = header_font
                    cell.alignment = Alignment(horizontal='left', vertical='top')
                
                # Write data - ensure all text is properly encoded
                for row_idx, row in enumerate(all_results, 2):
                    for col_idx, col_name in enumerate(COLUMNS, 1):
                        value = row[col_name]
                        # Ensure proper string encoding for text fields
                        if isinstance(value, str):
                            value = value.encode('utf-8', errors='ignore').decode('utf-8')
                        cell = ws.cell(row=row_idx, column=col_idx, value=value)
                        # Wrap text for content column
                        if col_name == 'content':
                            cell.alignment = Alignment(wrap_text=True, vertical='top')
                
                # Auto-adjust column widths
                for column in ws.columns:
                    max_length = 0
                    column_letter = column[0].column_letter
                    for cell in column:
                        try:
                            if cell.value and len(str(cell.value)) > max_length:
                                max_length = len(str(cell.value))
                        except:
                            pass
                    adjusted_width = min(max_length + 2, 100)  # Max width 100
                    ws.column_dimensions[column_letter].width = adjusted_width
                
                # Save the file with UTF-8 BOM for Excel compatibility
                wb.save(str(full_path))
                
                log_message(f"\n✅ Search completed in {total_time:.1f} seconds")
                log_message(f"   Found {len(all_results):,} results in {total_chunks} chunks")
                log_message(f"   Results saved to: {full_path}")
                log_message(f"   File encoding: UTF-8 (supports all languages)")
            else:
                log_message("\n🔍 No results found for the given criteria.")
                
    except Exception as e:
        log_message(f"\n❌ An error occurred during search: {e}")
        if 'conn' in locals() and conn is not None:
            conn.rollback()
    finally:
        # Close database connection
        if 'conn' in locals() and conn is not None:
            conn.close()
            log_message("✅ Database connection closed")

if __name__ == "__main__":
    main()
