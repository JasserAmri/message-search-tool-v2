import os
import psycopg2
from dotenv import load_dotenv

def check_table_columns():
    load_dotenv()
    
    try:
        conn = psycopg2.connect(
            host=os.getenv('DB_HOST'),
            port=os.getenv('DB_PORT'),
            dbname=os.getenv('DB_NAME'),
            user=os.getenv('DB_USER'),
            password=os.getenv('DB_PASSWORD'),
            sslmode=os.getenv('DB_SSLMODE')
        )
        
        with conn.cursor() as cur:
            # Get column names from msg_message table
            cur.execute("""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = 'msg_message';
            """)
            
            print("\nColumns in msg_message table:")
            print("-" * 50)
            for col in cur.fetchall():
                print(f"{col[0]} ({col[1]})")
            
            # Check if table exists and has data
            cur.execute("SELECT COUNT(*) FROM msg_message;")
            count = cur.fetchone()[0]
            print(f"\nTotal messages in msg_message: {count:,}")
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    check_table_columns()
