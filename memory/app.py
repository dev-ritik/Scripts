from datetime import datetime, timedelta

import dotenv
from flask import Flask, render_template, request

from common import get_events_for_date

app = Flask(__name__)


@app.route('/', methods=['GET', 'POST'])
def index():
    events = []
    if request.method == 'GET':
        on_date_str = request.args.get('date')
        seek_days = int(request.args.get('seek_days', 0))
        if not on_date_str:
            return "Missing date parameter", 400
        if seek_days < 0:
            seek_days = 0
        try:
            on_date = datetime.strptime(on_date_str, "%Y-%m-%d")
            date_list = [on_date + timedelta(days=delta) for delta in range(-seek_days, seek_days + 1)]

            all_events = []
            for date in date_list:
                daily_events = get_events_for_date(date)
                if daily_events:
                    all_events.extend(daily_events)

            events = sorted(all_events, key=lambda x: x['datetime'])

        except ValueError:
            return "Invalid date format", 400

    return render_template('index.html', events=events)


if __name__ == '__main__':
    dotenv.load_dotenv()
    app.run(debug=True)
