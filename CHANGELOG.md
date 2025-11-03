# Changelog

All notable changes to this project will be documented in this file.

## [2.0.0] - 2025-11-03

### 🎯 Major Features Added

#### Intelligent Auto-Optimization
- Automatic data sampling before search
- Smart chunk size selection (1-7 days based on density)
- Time and result estimation
- Adaptive limits based on data volume

#### Multi-Language Support
- UTF-8 Excel encoding with BOM
- Support for Arabic, Chinese, Japanese, and all languages
- Bold headers and text wrapping
- Auto-adjusted column widths

#### Enhanced Notifications
- Browser alert pop-ups on completion
- Sound notifications (success/info tones)
- Visual status badges (success/warning/error)
- System notifications (optional)

#### Improved File Management
- Auto-save to Downloads folder
- Custom filename support
- Multiple location search (current/logs/Downloads)
- Sanitized filenames

#### Detailed Logging
- Full SQL query display
- Sample results preview
- Query parameters logging
- Performance metrics
- Optimization decisions

#### Database Diagnostics
- DNS resolution testing
- Connection timeout detection
- Authentication error detection
- SSL/TLS error handling
- Detailed error messages with solutions

### 🐛 Bug Fixes
- Fixed download button not appearing without refresh
- Fixed 404 error on favicon.ico
- Fixed inline CSS warnings
- Fixed file download from Downloads folder
- Fixed log scrolling behavior

### 🎨 UI Improvements
- Removed all inline styles
- Added CSS classes for labels
- Better status badge styling
- Improved log display
- Auto-scroll only when at bottom

### 🧹 Project Cleanup
- Added comprehensive .gitignore
- Created GitHub-ready README
- Removed test scripts
- Added favicon
- Organized project structure

### 📝 Documentation
- Comprehensive README with badges
- Troubleshooting section
- Performance tips
- Database index recommendations
- Browser error explanations

## [1.0.0] - Initial Release

### Features
- Basic keyword search
- Date range filtering
- Excel export
- Web interface
- Real-time logging
- Dark/light mode
- Recent searches
