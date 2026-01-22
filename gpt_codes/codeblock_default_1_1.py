def log_message(message: str) -> None:
    """Log message to console_log.txt with timestamp"""
    # 파일이 닫혔는지 확인 후 쓰기 시도  ← 추가
    if _console_log_file.closed:
        return
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _console_log_file.write(f"[{timestamp}] {message}\n")
        _console_log_file.flush()
    except ValueError:
        # I/O operation on closed file 에러 무시  ← 추가
        pass