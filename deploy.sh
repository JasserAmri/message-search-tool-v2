#!/bin/bash

# Quick deployment script for message-search-tool

echo "==================================================="
echo "  Message Search Tool - Quick Deploy"
echo "==================================================="
echo ""

# Change to project directory
cd "C:\Users\JasserAMRI\OneDrive - QuickText\Desktop\message-search-tool"

echo "1. Checking git status..."
git status

echo ""
echo "2. Adding all changes..."
git add .

echo ""
echo "3. Committing changes..."
git commit -m "Fix: Function ordering, export_to_excel calls, indentation, and Vercel deployment config

- Moved log_message() and get_logs() to top of search_messages.py
- Fixed export_to_excel() call with proper output_path parameter
- Corrected indentation in main() function
- Added vercel.json for proper Vercel deployment
- Created wsgi.py as WSGI entry point
- Added gunicorn to requirements.txt
- Improved LOG_DIR detection for Vercel environment
- Added DEPLOYMENT.md and FIXES.md documentation"

echo ""
echo "4. Pushing to GitHub..."
git push origin main

echo ""
echo "==================================================="
echo "  ✅ Changes pushed successfully!"
echo "==================================================="
echo ""
echo "Next steps:"
echo "1. Go to your Vercel dashboard"
echo "2. Find message-search-tool project"
echo "3. Click 'Redeploy' to force rebuild"
echo "4. Or run: vercel --prod --force"
echo ""
echo "See DEPLOYMENT.md for detailed instructions"
