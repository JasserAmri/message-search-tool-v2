# Deployment Guide - Message Search Tool

## Fixed Issues

### 1. search_messages.py - Function Definition Order
**Problem**: Functions `log_message()` and `get_logs()` were defined at the end but called throughout the code  
**Fix**: Moved function definitions to the top of the file (lines 30-42)

### 2. search_messages.py - export_to_excel Call
**Problem**: `export_to_excel(all_results)` was missing the required `output_file` parameter  
**Fix**: Changed to `export_to_excel(all_results, output_path)` with proper path construction

### 3. search_messages.py - Indentation Issues
**Problem**: Improper indentation in main() function around the results processing block  
**Fix**: Corrected indentation and added proper try/finally blocks with pbar.close()

### 4. Missing vercel.json
**Problem**: Vercel deployment needs configuration file  
**Fix**: Created vercel.json with proper Python build settings

### 5. requirements.txt
**Problem**: Missing gunicorn for production deployment  
**Fix**: Added gunicorn>=20.1.0 to requirements

### 6. WSGI Entry Point
**Problem**: No proper WSGI entry point for Vercel  
**Fix**: Created wsgi.py and added `application = app` export in app.py

### 7. LOG_DIR Environment Detection
**Problem**: LOG_DIR detection for Vercel was incomplete  
**Fix**: Added VERCEL_ENV check and better error handling

## Deployment Steps

### 1. Commit Changes to Git

```bash
cd "C:\Users\JasserAMRI\OneDrive - QuickText\Desktop\message-search-tool"
git add .
git commit -m "Fix: Correct function ordering, export_to_excel calls, and Vercel deployment config"
git push origin main
```

### 2. Force Redeploy on Vercel

Option A - Via Vercel Dashboard:
1. Go to your Vercel dashboard
2. Find the message-search-tool project
3. Click on the latest deployment
4. Click "Redeploy" button
5. Check "Use existing Build Cache" or leave unchecked for fresh build

Option B - Via Vercel CLI:
```bash
vercel --prod --force
```

### 3. Environment Variables on Vercel

Make sure these are set in Vercel dashboard (Settings > Environment Variables):
- `DB_HOST`
- `DB_PORT`
- `DB_NAME`
- `DB_USER`
- `DB_PASSWORD`
- `DB_SSLMODE`

### 4. Verify Deployment

After deployment:
1. Check the deployment logs in Vercel dashboard
2. Visit your deployed URL
3. Test a simple search with small date range
4. Check if logs are appearing

## Known Limitations on Vercel

### Serverless Environment Constraints:
1. **Logs location**: Uses /tmp/logs (ephemeral, clears between invocations)
2. **Excel files**: Saved to /tmp, not persistent
3. **Timeout**: Vercel free tier has 10s execution limit, Pro has 60s
4. **Memory**: Limited to 1024MB on free tier

### Workarounds:
- For long searches: Consider splitting into smaller date ranges
- For persistence: Integrate with external storage (S3, Cloudflare R2, etc.)
- For large datasets: Consider moving to dedicated server or Docker container

## Testing Checklist

- [ ] App loads at deployed URL
- [ ] Search form accepts input
- [ ] Search starts and shows logs
- [ ] Results are found and displayed
- [ ] Download link works (even if temporary)
- [ ] Recent searches list updates
- [ ] Theme toggle works
- [ ] No console errors (except browser extension warnings)

## Rollback Plan

If deployment fails:
```bash
git revert HEAD
git push origin main
```

Vercel will automatically deploy the previous working version.

## Additional Recommendations

### For Production:
1. Add Sentry or similar for error tracking
2. Implement proper logging service (Logtail, Papertrail)
3. Use external storage for Excel files (AWS S3, Cloudflare R2)
4. Add rate limiting to prevent abuse
5. Implement user authentication if needed
6. Add caching for frequently accessed data

### For Performance:
1. Database: Ensure indexes on msg_message(created_at, content)
2. Consider Redis for caching search results
3. Implement pagination for large result sets
4. Add query timeout configuration

## Support

If issues persist:
1. Check Vercel deployment logs
2. Verify environment variables are set
3. Test database connection from local environment
4. Check browser console for client-side errors
5. Review /api/logs endpoint for server-side logs
