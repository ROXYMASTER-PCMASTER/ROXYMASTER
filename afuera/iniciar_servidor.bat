@echo off
cd /d c:\Users\PCMASTER\Desktop\roxymaster\pcmaster
python -c "import sys; sys.path.insert(0,'scripts'); import uvicorn; uvicorn.run('server:app', host='0.0.0.0', port=8086, log_level='info')"