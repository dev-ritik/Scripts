from datetime import datetime, timedelta

import dotenv
from flask import Flask, render_template, request, send_file, make_response
from common import get_events_for_date, get_user_dp

app = Flask(__name__)


@app.route('/', methods=['GET', 'POST'])
def index():
    events = []
    if request.method == 'GET':
        on_date_str = request.args.get('date')
        seek_days = int(request.args.get('seek_days', 0))
        group = request.args.get('group', 'true') == 'true'

        if not on_date_str:
            return "Missing date parameter", 400
        seek_days = 0 if seek_days < 0 else seek_days
        try:
            on_date = datetime.strptime(on_date_str, "%Y-%m-%d")
        except ValueError:
            return "Invalid date format", 400

        date_list = [on_date + timedelta(days=delta) for delta in range(-seek_days, seek_days + 1)]

        all_events = []
        for date in date_list:
            daily_events = get_events_for_date(date, ignore_groups=not group)
            if daily_events:
                all_events.extend(daily_events)

        events = sorted(all_events, key=lambda x: x['datetime'])

    return render_template('index.html', events=events)


@app.route('/user/dp/<display_name>')
def user_dp(display_name):
    dp_path = get_user_dp(display_name)
    if not dp_path:
        return "Display picture not found", 404

    response = make_response(send_file(dp_path))
    # Cache for 24 hours
    response.headers['Cache-Control'] = 'public, max-age=86400'
    return response


if __name__ == '__main__':
    dotenv.load_dotenv()
    app.run(debug=True)