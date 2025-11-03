# Message Keyword Search Tool

A powerful, intelligent PostgreSQL message search tool with a modern web interface, auto-optimization, and multi-language support.

![Python](https://img.shields.io/badge/python-3.7+-blue.svg)
![Flask](https://img.shields.io/badge/flask-2.0+-green.svg)
![PostgreSQL](https://img.shields.io/badge/postgresql-12+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

## ✨ Features

### 🎯 Intelligent Search
- **Auto-Optimization**: Automatically samples data and optimizes chunk size
- **Adaptive Chunking**: Adjusts strategy based on data density
- **Smart Estimates**: Predicts total time and results before searching
- **Multi-Keyword**: Search for multiple keywords simultaneously

### 🌐 Modern Web Interface
- **Real-time Progress**: Live logs and progress tracking
- **Dark/Light Mode**: Beautiful themes for any preference
- **Responsive Design**: Works on desktop, tablet, and mobile
- **Recent Searches**: Quick access to previous searches

### 🔔 Smart Notifications
- **Browser Alerts**: Pop-up notifications when search completes
- **Sound Alerts**: Pleasant audio notifications
- **Visual Status**: Color-coded badges for success/warning/error
- **System Notifications**: Native OS notifications (optional)

### 🌍 Multi-Language Support
- **UTF-8 Excel Export**: Supports Arabic, Chinese, Japanese, etc.
- **Proper Encoding**: No more garbled text
- **Auto-formatting**: Bold headers, text wrapping, adjusted columns

### 💾 Smart File Management
- **Auto-save to Downloads**: Files go to Downloads folder automatically
- **Custom Filenames**: Name your exports whatever you want
- **Multiple Locations**: Searches current dir, logs, and Downloads

### 📊 Detailed Logging
- **SQL Queries**: See exactly what queries are running
- **Sample Results**: Preview results in logs
- **Performance Metrics**: Query times and result counts
- **Error Diagnostics**: Detailed error messages with solutions

## 🚀 Quick Start

### Prerequisites

- Python 3.7 or higher
- PostgreSQL database access
- Internet connection (for database access)

### Installation

1. **Clone the repository**

```bash
git clone https://github.com/yourusername/message-search-tool.git
cd message-search-tool
```

2. **Install dependencies**

```bash
pip install -r requirements.txt
```

3. **Configure database**

Create a `.env` file in the project root:

```env
# Database Configuration
DB_HOST=your_database_host.com
DB_PORT=5432
DB_NAME=your_database_name
DB_USER=your_username
DB_PASSWORD=your_password
DB_SSLMODE=require
```

4. **Run the application**

```bash
python app.py
```

5. **Open your browser**

Navigate to `http://localhost:5000`

## 📖 Usage

### Web Interface

1. **Enter Keywords**: Type keywords separated by commas (e.g., `shisha, hookah, smoking`)
2. **Select Date Range**: Choose start and end dates
3. **Optional Settings**:
   - Initial chunk size (auto-optimized)
   - Max results per chunk
   - Custom export filename
4. **Start Search**: Click "Start Search" and watch real-time progress
5. **Download Results**: Click download button when complete

### Auto-Optimization

The tool automatically:
- Samples your data (1 day in middle of range)
- Analyzes result density
- Chooses optimal chunk size (1-7 days)
- Estimates total time and results
- Adjusts limits if needed

**Optimization Logic:**
```
No results        → 7-day chunks (fast)
< 100/day         → 7-day chunks (low density)
100-1000/day      → 5-day chunks (medium)
1000-5000/day     → 3-day chunks (high)
> 5000/day        → 1-day chunks (very high)
```

## 📁 Project Structure

```
message-search-tool/
├── app.py                          # Flask web application
├── search_messages.py              # Core search logic
├── requirements.txt                # Python dependencies
├── .env                           # Database configuration (create this)
├── .gitignore                     # Git ignore rules
├── README.md                      # This file
├── static/
│   ├── style.css                  # Application styles
│   └── favicon.ico                # Favicon
├── templates/
│   └── index.html                 # Web interface
└── logs/                          # Search logs (auto-created)
```

## 🔧 Configuration

### Environment Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `DB_HOST` | Database hostname | - | ✅ |
| `DB_PORT` | Database port | 5432 | ❌ |
| `DB_NAME` | Database name | - | ✅ |
| `DB_USER` | Database username | - | ✅ |
| `DB_PASSWORD` | Database password | - | ✅ |
| `DB_SSLMODE` | SSL mode | require | ❌ |

### Search Parameters

- **Keywords**: Comma-separated list of keywords to search
- **Date Range**: Start and end dates for search
- **Chunk Size**: Days per chunk (auto-optimized)
- **Limit**: Max results per chunk (auto-adjusted)
- **Filename**: Custom export filename (optional)

## 📊 Output Format

Results are exported to Excel (`.xlsx`) with:

- **Columns**: id, created_at, content, conversation_id, trigger, user_id
- **Encoding**: UTF-8 with BOM (supports all languages)
- **Formatting**: Bold headers, text wrapping, auto-width
- **Location**: Downloads folder (or current directory)

## 🐛 Troubleshooting

### Database Connection Issues

The tool provides detailed diagnostics:

- ❌ **DNS resolution failed** → Check internet/hostname
- ❌ **Authentication failed** → Check username/password
- ❌ **Connection timeout** → Check firewall/network
- ❌ **SSL error** → Check SSL mode setting
- ❌ **Permission denied** → Check database permissions

### Performance Issues

- **Slow queries**: Database needs indexes (see recommendations)
- **Timeouts**: Use smaller date ranges or 1-day chunks
- **Too many results**: Add more specific keywords

### Browser Errors

The browser console errors you see are from browser extensions (not the app):
- `sw.js` errors → Browser extension issue
- `runtime.lastError` → Extension cache issue
- `Permissions policy violation` → Extension trying to use deprecated APIs

**These are harmless and don't affect the app.**

## 🎯 Performance Tips

### Current Performance
- **126M+ messages** in database
- **~60-70 seconds** per day chunk
- **Auto-optimization** reduces time by 3x for rare keywords

### Recommended Database Indexes

For optimal performance, ask your DBA to add:

```sql
-- Index on created_at (most important!)
CREATE INDEX idx_msg_message_created_at 
ON msg_message(created_at) 
WHERE trigger = 2 AND deleted_at IS NULL;

-- Full-text search index (best for keywords)
CREATE INDEX idx_msg_message_content_fts 
ON msg_message USING GIN(to_tsvector('english', content))
WHERE trigger = 2 AND deleted_at IS NULL;
```

**Expected speedup: 12-70x faster!**

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📝 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🙏 Acknowledgments

- Built with Flask, PostgreSQL, and openpyxl
- UI powered by Tailwind CSS and Font Awesome
- Inspired by the need for efficient message analysis

## 📧 Support

For issues, questions, or suggestions, please open an issue on GitHub.

---

**Made with ❤️ for efficient message searching**

## Use Cases

- Find smoking/vaping policy inquiries
- Search amenity-related questions
- Analyze customer message patterns
- Extract messages by keyword for analysis

## Setup

1. **Install dependencies**:

```bash
pip install -r requirements.txt
```

2. **Configure database**:

```bash
cp .env.example .env
# Edit .env with your database credentials
```

3. **Run the web interface**:

```bash
python app.py
```

4. **Open your browser**:

```text
http://localhost:5000
```

## Web Interface

The web interface allows you to:

- Enter keywords (comma-separated)
- Select custom date range with date pickers
- Configure chunk size (default: 3 days)
- Set max results per chunk (default: 20,000)
- View real-time search logs
- Download results as Excel files
- View history of recent searches

## Configuration

All configuration is done through the web interface. Advanced settings:

- **Chunk Size**: Initial number of days to process per query (1-7 days)
- **Max Results per Chunk**: Safety limit to prevent memory issues (default: 20,000)
- **Date Range**: Select any start and end date for your search

The tool automatically adjusts chunk size based on query performance:

- Slow queries (>30s) → reduces chunk size
- Fast queries (<30s) → increases chunk size

## Output

Creates: `keyword_results_YYYYMMDD_HHMMSS.xlsx` in the project directory

Columns included:

- `id`: Message ID
- `created_at`: Timestamp
- `content`: Message text
- `conversation_id`: Conversation reference
- `trigger`: Message trigger type
- `user_id`: User reference

## Command Line Usage (Optional)

You can also run searches directly from command line:

```bash
# Set environment variables
export KEYWORDS="smoke,smoking"
export START_DATE="2024-01-01T00:00:00"
export END_DATE="2024-12-31T23:59:59"
export CHUNK_DAYS="3"
export LIMIT_PER_CHUNK="20000"

# Run search
python search_messages.py
```

## How It Works

1. Splits the search period into configurable chunks (default: 3 days)
2. Each query searches one chunk with ILIKE pattern matching
3. Automatically adjusts chunk size based on query performance
4. Combines results into a single Excel file
5. Shows detailed progress and logs in real-time

## Troubleshooting

**Timeout errors**: The tool automatically reduces chunk size when queries are slow  
**Out of memory**: Reduce "Max Results per Chunk" in the web interface  
**No results**: Check keyword spelling and verify date range  
**Logs not updating**: Refresh the page or check browser console for errors  
**Connection failed**: Ensure Flask server is running on port 5000
