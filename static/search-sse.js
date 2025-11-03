/**
 * Enhanced Search UI with SSE Streaming, Progress Tracking, and Cancel Button
 */

class SearchUI {
    constructor() {
        this.currentSearchId = null;
        this.eventSource = null;
        this.isSearching = false;
    }

    startSearch(searchId) {
        this.currentSearchId = searchId;
        this.isSearching = true;
        
        // Show cancel button
        const cancelBtn = document.getElementById('cancelSearchBtn');
        if (cancelBtn) {
            cancelBtn.style.display = 'inline-block';
            cancelBtn.onclick = () => this.cancelSearch();
        }
        
        // Connect to SSE stream
        this.connectSSE(searchId);
    }

    connectSSE(searchId) {
        // Close existing connection if any
        if (this.eventSource) {
            this.eventSource.close();
        }

        // Create new EventSource
        this.eventSource = new EventSource(`/api/search/stream/${searchId}`);

        this.eventSource.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                this.handleMessage(data);
            } catch (e) {
                console.error('Error parsing SSE message:', e);
            }
        };

        this.eventSource.onerror = (error) => {
            console.error('SSE error:', error);
            this.eventSource.close();
            
            // Fall back to polling if SSE fails
            if (this.isSearching) {
                console.log('Falling back to polling...');
                this.fallbackToPolling(searchId);
            }
        };
    }

    handleMessage(data) {
        // Update logs
        if (data.message) {
            this.appendLog(data.message);
        }

        // Update progress bar if progress data available
        if (data.progress !== undefined) {
            this.updateProgress(data);
        }

        // Handle errors
        if (data.type === 'error') {
            this.handleError(data.message);
        }

        // Handle completion
        if (data.type === 'complete' || data.message?.includes('Search completed')) {
            this.handleComplete(data);
        }
    }

    updateProgress(data) {
        const progressBar = document.getElementById('progressBar');
        const progressText = document.getElementById('progressText');
        const progressTime = document.getElementById('progressTime');

        if (progressBar) {
            progressBar.style.width = `${data.progress || 0}%`;
        }

        if (progressText && data.current_chunk && data.estimated_chunks) {
            progressText.textContent = `Chunk ${data.current_chunk}/${data.estimated_chunks} (${data.progress}%) - ${data.results_so_far || 0} results`;
        }

        if (progressTime && data.eta) {
            progressTime.textContent = `ETA: ${data.eta}`;
        }
    }

    appendLog(message) {
        const logsDiv = document.getElementById('logContainer');
        if (!logsDiv) return;

        const logEntry = document.createElement('div');
        logEntry.className = 'log-entry';
        
        // Determine log type for styling
        let type = 'info';
        const msgLower = message.toLowerCase();
        if (msgLower.includes('error') || msgLower.includes('❌') || msgLower.includes('failed')) {
            type = 'error';
        } else if (msgLower.includes('warn') || msgLower.includes('⚠️')) {
            type = 'warning';
        } else if (msgLower.includes('success') || msgLower.includes('✅') || msgLower.includes('completed')) {
            type = 'success';
        }
        
        // Add special classes for different content types
        if (msgLower.includes('select') && msgLower.includes('from')) {
            type = 'info sql-query';
        } else if (msgLower.includes('chunk') && msgLower.includes('%')) {
            type = 'info progress-info';
        } else if (msgLower.includes('database') || msgLower.includes('connection')) {
            type = 'info db-info';
        }
        
        logEntry.className = `log-entry ${type}`;
        
        // Format message with better styling
        let formattedMsg = message;
        
        // Add timestamp if not present
        if (!message.match(/\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}/)) {
            const timestamp = new Date().toLocaleTimeString();
            formattedMsg = `[${timestamp}] ${message}`;
        }
        
        // Highlight important patterns
        formattedMsg = formattedMsg
            // SQL keywords
            .replace(/\b(SELECT|FROM|WHERE|AND|OR|LIMIT|BETWEEN|ILIKE)\b/g, '<span style="color: #a78bfa; font-weight: 600;">$1</span>')
            // Numbers and statistics
            .replace(/(\d{1,3}(?:,\d{3})*)/g, '<span style="color: #60a5fa; font-weight: 600;">$1</span>')
            // File paths
            .replace(/([\/\\][\w\-\/\\.:]+\.(xlsx|log|json))/gi, '<span style="color: #34d399; font-weight: 500;">$1</span>')
            // Percentages
            .replace(/(\d+)%/g, '<span style="color: #fbbf24; font-weight: 600;">$1%</span>')
            // Time durations
            .replace(/(\d+\.\d+s|\d+m \d+s|\d+:\d+:\d+)/g, '<span style="color: #f472b6;">$1</span>')
            // Preserve indentation
            .replace(/^(   )/gm, '&nbsp;&nbsp;&nbsp;')
            .replace(/^(      )/gm, '&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;')
            .replace(/\n/g, '<br>');
        
        logEntry.innerHTML = formattedMsg;
        logsDiv.appendChild(logEntry);
        
        // Auto-scroll to bottom
        logsDiv.scrollTop = logsDiv.scrollHeight;
    }

    async cancelSearch() {
        if (!this.currentSearchId) return;

        try {
            const response = await fetch(`/api/search/cancel/${this.currentSearchId}`, {
                method: 'POST'
            });

            if (response.ok) {
                this.appendLog('🛑 Cancelling search...');
                this.handleCancelled();
            }
        } catch (error) {
            console.error('Error cancelling search:', error);
        }
    }

    handleCancelled() {
        this.isSearching = false;
        
        if (this.eventSource) {
            this.eventSource.close();
            this.eventSource = null;
        }

        const cancelBtn = document.getElementById('cancelSearchBtn');
        if (cancelBtn) {
            cancelBtn.style.display = 'none';
        }

        const statusDiv = document.getElementById('searchStatus');
        if (statusDiv) {
            statusDiv.textContent = 'Cancelled';
            statusDiv.className = 'status-badge cancelled';
        }
    }

    handleComplete(data) {
        this.isSearching = false;

        if (this.eventSource) {
            this.eventSource.close();
            this.eventSource = null;
        }

        const cancelBtn = document.getElementById('cancelSearchBtn');
        if (cancelBtn) {
            cancelBtn.style.display = 'none';
        }

        const statusDiv = document.getElementById('searchStatus');
        if (statusDiv) {
            statusDiv.textContent = 'Completed';
            statusDiv.className = 'status-badge success';
        }

        // Show download button if filename is provided
        if (data.filename) {
            this.showDownloadButton(data.filename);
        }
    }

    handleError(message) {
        this.isSearching = false;

        if (this.eventSource) {
            this.eventSource.close();
            this.eventSource = null;
        }

        const statusDiv = document.getElementById('searchStatus');
        if (statusDiv) {
            statusDiv.textContent = 'Error';
            statusDiv.className = 'status-badge error';
        }

        alert(`Search error: ${message}`);
    }

    fallbackToPolling(searchId) {
        console.log('⚠️ SSE failed, falling back to polling');
        this.appendLog('⚠️ Real-time streaming unavailable, using polling mode (updates every 2s)');
        
        let lastLogLength = 0;
        
        const interval = setInterval(async () => {
            if (!this.isSearching) {
                clearInterval(interval);
                return;
            }

            try {
                const response = await fetch(`/api/logs/${searchId}`);
                const logs = await response.text();
                
                // Only append new logs
                const logLines = logs.split('\n').filter(line => line.trim());
                if (logLines.length > lastLogLength) {
                    for (let i = lastLogLength; i < logLines.length; i++) {
                        this.appendLog(logLines[i]);
                    }
                    lastLogLength = logLines.length;
                }
                
                // Check if completed
                if (logs.includes('Search completed')) {
                    clearInterval(interval);
                    this.handleComplete({});
                }
            } catch (error) {
                console.error('Polling error:', error);
            }
        }, 2000);
    }

    showDownloadButton(filename) {
        const downloadDiv = document.getElementById('searchResults');
        if (downloadDiv) {
            downloadDiv.style.display = 'block';
            const downloadLink = document.getElementById('downloadLink');
            if (downloadLink) {
                downloadLink.href = `/download/${filename}`;
            }
        }
    }
}

// Initialize
const searchUI = new SearchUI();

// Export for use in main script
window.searchUI = searchUI;
