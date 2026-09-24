from app import create_app

app = create_app()

if __name__ == "__main__":
    # 5000 is often taken by macOS's AirPlay Receiver, and Paradise City
    # Music's own run.py uses 5050 -- 5051 lets both run side by side.
    app.run(debug=True, host="127.0.0.1", port=5051)
