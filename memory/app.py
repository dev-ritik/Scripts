import init

# This should be the first line in the file. It initializes the app.
init.init()

from datetime import datetime, timedelta

from flask import Flask, render_template, request, send_file, make_response

from common import get_user_dp, MemoryAggregator

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

        events = MemoryAggregator.get_events_for_dates(on_date - timedelta(seek_days),
                                                       on_date + timedelta(seek_days), ignore_groups=not group)

        events.sort(key=lambda x: x['datetime'])

    return render_template('index.html', events=events)


@app.route('/user/dp/<name>')
def user_dp(name):
    dp_path = get_user_dp(name)
    if not dp_path:
        return "Display picture not found", 404

    response = make_response(send_file(dp_path))
    # Cache for 24 hours
    response.headers['Cache-Control'] = 'public, max-age=86400'
    return response


@app.route('/asset/<provider>/<file_id>')
def asset(provider, file_id):
    asset, mime_type = MemoryAggregator.get_instance().get_asset(provider, file_id)
    if not asset:
        return "Asset not found", 404
    # Cache for 24 hours
    response = make_response(asset)
    response.headers['Cache-Control'] = 'public, max-age=86400'
    response.headers['Content-Type'] = mime_type
    # with open('test_image.webp', 'wb') as f:
    #     f.write(asset)
    return response


if __name__ == '__main__':
    app.run(debug=True)