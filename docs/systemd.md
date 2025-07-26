# Systemd Service Management

## List Services
```bash
# List all services
sudo systemctl list-units --type=service

# List running services only
sudo systemctl list-units --type=service --state=running

# List all services (including inactive)
sudo systemctl list-unit-files --type=service
```

## Service Control
```bash
# Start a service
sudo systemctl start service-name

# Stop a service
sudo systemctl stop service-name

# Restart a service
sudo systemctl restart service-name

# Reload configuration without restart
sudo systemctl reload service-name

# Enable service to start on boot
sudo systemctl enable service-name

# Disable service from starting on boot
sudo systemctl disable service-name
```

## Service Status
```bash
# Check service status
sudo systemctl status service-name

# Check if service is active
sudo systemctl is-active service-name

# Check if service is enabled
sudo systemctl is-enabled service-name
```

## Logs
```bash
# View service logs
sudo journalctl -u service-name

# View recent logs with follow
sudo journalctl -u service-name -f

# View logs from last boot
sudo journalctl -u service-name -b
```

## Common Services
```bash
# Web server
sudo systemctl restart nginx

# API service (project specific)
sudo systemctl restart intherock-api

# SSH daemon
sudo systemctl restart ssh
```

## Service Files
- Location: `/etc/systemd/system/`
- Reload after changes: `sudo systemctl daemon-reload`