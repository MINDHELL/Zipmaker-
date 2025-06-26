import threading
from zip_bot import bot
from health_check import run_dummy_server

if __name__ == "__main__":
    # Start health check Flask server in background
    threading.Thread(target=run_dummy_server, daemon=True).start()
    
    # Run the Telegram bot
    bot.run()
