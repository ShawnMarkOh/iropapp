document.addEventListener('DOMContentLoaded', () => {
    const logContainer = document.getElementById('log-container');
    const socket = io('/logs');

    function addLogLine(line) {
        const atBottom = logContainer.scrollTop + logContainer.clientHeight >= logContainer.scrollHeight - 20;

        const lineEl = document.createElement('span');
        // Sanitize line to prevent HTML injection
        lineEl.textContent = line;

        if (line.includes('ERROR')) {
            lineEl.className = 'log-line-error';
        } else if (line.includes('WARNING')) {
            lineEl.className = 'log-line-warning';
        }
        
        logContainer.appendChild(lineEl);

        if (atBottom) {
            logContainer.scrollTop = logContainer.scrollHeight;
        }
    }

    socket.on('connect', () => {
        console.log('Connected to log stream.');
        logContainer.textContent = 'Connected to log stream. Waiting for logs...\n';
    });

    socket.on('disconnect', () => {
        console.log('Disconnected from log stream.');
        addLogLine('--- DISCONNECTED FROM LOG STREAM ---');
    });

    socket.on('connect_error', (err) => {
        console.error('Log stream connection error:', err);
        logContainer.textContent = `Connection to log stream failed: ${err.message}. You may need to log in again.`;
    });

    socket.on('initial_logs', (data) => {
        logContainer.textContent = ''; // Clear "Connecting..." message
        data.lines.forEach(line => {
            addLogLine(line);
        });
    });

    socket.on('new_log_line', (data) => {
        data.lines.forEach(line => {
            addLogLine(line);
        });
    });
});
