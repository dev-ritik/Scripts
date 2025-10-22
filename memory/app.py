import asyncio

import init

# This should be the first line in the file. It initializes the app.
init.init()

import mimetypes

import aiofiles

from datetime import datetime, timedelta

from flask import Flask, render_template, request, send_file, make_response, jsonify

from common import get_user_dp, MemoryAggregator, get_profile_json

app = Flask(__name__)


@app.route('/', methods=['GET', 'POST'])
async def index():
    events = []
    if request.method == 'GET':
        on_date_str = request.args.get('date')
        seek_days = int(request.args.get('seek_days', 0))
        group = request.args.get('group', 'true') == 'true'
        providers_param = request.args.get('providers')  # comma-separated list

        if not on_date_str:
            return render_template('index.html', events=[])

        seek_days = 0 if seek_days < 0 else seek_days
        try:
            on_date = datetime.strptime(on_date_str, "%Y-%m-%d").date()
        except ValueError:
            return "Invalid date format", 400

        providers = [p.strip() for p in providers_param.split(",") if p.strip()] if providers_param else None

        events = await MemoryAggregator.get_events_for_dates(on_date - timedelta(days=seek_days),
                                                             on_date + timedelta(days=seek_days),
                                                             ignore_groups=not group,
                                                             providers=providers)

        events.sort(key=lambda x: x.datetime)

    return render_template('index.html', events=[event.to_dict() for event in events])


@app.route("/status")
async def status():
    aggregator = MemoryAggregator.get_instance()

    async def gather_provider_info(provider, instance):
        try:
            start_date, end_date = await instance.get_start_end_date()
            return provider, {
                "start_date": start_date,
                "end_date": end_date,
                "available": instance.is_working(),
                "logo": instance.get_logo()
            }
        except Exception as e:
            # graceful failure
            return provider, {
                "start_date": None,
                "end_date": None,
                "available": False,
                "logo": instance.get_logo(),
                "error": str(e)
            }

    tasks = [
        gather_provider_info(provider, instance)
        for provider, instance in aggregator.providers.items()
    ]

    results = await asyncio.gather(*tasks)
    providers = dict(results)

    return render_template("status.html", providers=providers)


@app.route("/people")
async def people_page():
    return render_template("people.html")


@app.route("/people_data")
async def people_data():
    data = list((await get_profile_json()).values())
    data.sort(key=lambda x: x['display_name'])
    return jsonify(data)


@app.route('/user/dp/<name>')
async def user_dp(name):
    dp_path = await get_user_dp(name)
    if not dp_path:
        return "Display picture not found", 404

    response = make_response(send_file(dp_path))
    # Cache for 24 hours
    response.headers['Cache-Control'] = 'public, max-age=86400'
    return response


@app.route('/asset/<provider>/<file_id>')
async def asset(provider, file_id):
    if file_id == 'logo.png':
        media_file_path = f'assets/logos/{provider}.png'
        mime_type, _ = mimetypes.guess_type(media_file_path)
        async with aiofiles.open(media_file_path, "rb") as media_file:
            media_data = await media_file.read()
        return media_data, mime_type

        return "Asset not found", 404
    asset, mime_type = await MemoryAggregator.get_instance().get_asset(provider, file_id)
    if not asset:
        return "Asset not found", 404
    # Cache for 24 hours
    response = make_response(asset)
    response.headers['Cache-Control'] = 'public, max-age=86400'
    response.headers['Content-Type'] = mime_type
    # with open('test_image.webp', 'wb') as f:
    #     f.write(asset)
    return response


@app.route('/available_providers')
async def get_available_providers():
    return [provider_name for provider_name, instance in MemoryAggregator.get_instance().providers.items() if
            instance.is_working()]

if __name__ == '__main__':
    app.run(debug=True)