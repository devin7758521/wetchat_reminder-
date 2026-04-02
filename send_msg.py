name: Stock Reminder

on:
  workflow_dispatch:
  schedule:
    - cron: '30 1 * * 1-5'   # 北京时间 09:30 (早盘)
    - cron: '45 6 * * 1-5'   # 北京时间 14:45 (尾盘)

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout Code
        uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.10'

      - name: Install Dependencies
        run: |
          pip install pandas requests akshare

      - name: Part 1 Scan
        env:
          WECHAT_WEBHOOK_KEY: ${{ secrets.WECHAT_WEBHOOK_KEY }}
        run: |
          # 增加重试逻辑，防止瞬时网络抖动
          python send_msg.py 1 || (sleep 15 && python send_msg.py 1)

      - name: Part 2 Scan
        run: |
          python send_msg.py 2 || (sleep 15 && python send_msg.py 2)

      - name: AI Summary
        env:
          WECHAT_WEBHOOK_KEY: ${{ secrets.WECHAT_WEBHOOK_KEY }}
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
        run: |
          python send_msg.py summary || (sleep 15 && python send_msg.py summary)
