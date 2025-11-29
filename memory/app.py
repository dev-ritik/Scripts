import asyncio
import os
import string
from collections import defaultdict, Counter
from urllib.parse import unquote

import pandas as pd

import configs
import init
from configs import COMMON_WORDS_FOR_USER_STATS, USER
from provider.base_provider import MediaType
from utils import add_caching_to_response

# This should be the first line in the file. It initializes the app.
init.init()

import mimetypes

import aiofiles

from datetime import datetime

from flask import Flask, render_template, request, send_file, make_response, jsonify

from common import MemoryAggregator
from profile import get_user_dp, get_profile_json, get_user_profile_from_name

app = Flask(__name__)


@app.route('/', methods=['GET'])
async def index():
    return add_caching_to_response(render_template('index.html', events=[]))

@app.route('/chat_data')
async def chat_data():
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")

    start_date = datetime.strptime(start_date, "%Y-%m-%d").date() if start_date else None
    end_date = datetime.strptime(end_date, "%Y-%m-%d").date() if end_date else None

    if not start_date or not end_date or end_date < start_date:
        return f"Invalid date format {start_date} {end_date}", 400

    group = request.args.get('group', 'true') == 'true'
    search = unquote(request.args.get('search')) if request.args.get('search') else None
    providers_param = request.args.get('providers')  # comma-separated list
    peoples_param = request.args.get('peoples')  # comma-separated list

    providers = [p.strip() for p in providers_param.split(",") if p.strip()] if providers_param else None
    peoples = [p.strip() for p in peoples_param.split(",") if p.strip()] if peoples_param else []

    for people in peoples:
        user_profile = await get_user_profile_from_name(people)
        if not user_profile:
            return jsonify({"error": "User not found"}), 404

    events = await MemoryAggregator.get_events_for_dates(start_date,
                                                         end_date,
                                                         ignore_groups=not group,
                                                         providers=providers,
                                                         senders=peoples,
                                                         search=search)

    events.sort(key=lambda x: x.datetime)

    return add_caching_to_response(jsonify([event.to_dict() for event in events]))


@app.route("/status")
async def status():
    return add_caching_to_response(render_template("status.html"))


@app.route("/status_data")
async def status_data():
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

    return add_caching_to_response(jsonify(providers), 20)


@app.route("/people")
async def people_page():
    return add_caching_to_response(render_template("people.html"))


@app.route("/people_data")
async def people_data():
    data = list((await get_profile_json()).values())
    data.sort(key=lambda x: x['display_name'])
    return add_caching_to_response(jsonify(data))


@app.route("/circles")
def circles_page():
    return add_caching_to_response(render_template("circles.html"))


@app.route("/circle_data")
async def circle_data():
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")

    start_date = datetime.strptime(start_date, "%Y-%m-%d").date() if start_date else None
    end_date = datetime.strptime(end_date, "%Y-%m-%d").date() if end_date else None

    if not start_date or not end_date or end_date < start_date:
        print(start_date, end_date)
        return f"Invalid date format {start_date} {end_date}", 400

    messages_by_sender = await MemoryAggregator.get_instance().get_messages_by_sender(
        start_date,
        end_date,
        ignore_groups=True)

    messages_by_sender.pop(configs.USER, None)

    message_count_by_sender = {}
    sender_weekly_counts = {}

    for sender, messages in messages_by_sender.items():
        message_count_by_sender[sender] = len(messages)
        words_counter = defaultdict(int)

        # bucket messages by ISO week
        weekly_counts = defaultdict(int)
        for message in messages:
            if message.message and message.media_type != MediaType.NON_TEXT:
                words = message.message.split()
                for word in words:
                    if len(word) == 1 and (word.isdigit() or word in string.punctuation):
                        continue
                    words_counter[word] += 1

                if message.datetime:
                    year_week = message.datetime.strftime("%Y-%W")
                    weekly_counts[year_week] += 1

        sender_weekly_counts[sender] = dict(weekly_counts)

    # Get the top 15 most active people
    top_15_people = sorted(message_count_by_sender.items(), key=lambda x: x[1], reverse=True)[:15]

    people = []
    for name, chat_count in top_15_people:
        weekly_series = (
            pd.Series(sender_weekly_counts.get(name, {}))
            .sort_index()
            .astype(int)
        )
        moving_avg_series = (
            weekly_series.rolling(window=3, min_periods=1).mean().round(2)
        )

        weekly_counts_dict = {k: int(v) for k, v in weekly_series.to_dict().items()}
        moving_avg_dict = {k: float(v) for k, v in moving_avg_series.to_dict().items()}

        people.append({
            "name": name,
            "dp": f"/user/dp/{name}",
            "chats": chat_count,
            "chat_times": {
                "weekly_counts": weekly_counts_dict,
                "weekly_moving_avg": moving_avg_dict
            }
        })

    return add_caching_to_response(jsonify({"people": people}), 3600, 30)


@app.route("/user/stats/<name>")
async def get_user_stats(name):
    """
    Returns most common words used by the user.
    Example: GET /user/stats/Alice
    """
    start_date_str = request.args.get("start_date")
    end_date_str = request.args.get("end_date")

    # Parse and validate dates
    try:
        start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date() if start_date_str else None
        end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date() if end_date_str else None
    except ValueError:
        return jsonify({"error": "Invalid date format, use YYYY-MM-DD"}), 400

    user_profile = await get_user_profile_from_name(name)
    if not user_profile:
        return jsonify({"error": "User not found"}), 404

    messages_by_sender = await MemoryAggregator.get_instance().get_messages_by_sender(
        start_date,
        end_date,
        ignore_groups=True,
        ignore_media_type=MediaType.NON_TEXT,
        senders=name)

    if not messages_by_sender:
        print(f"No messages found for user {user_profile.get('display_name')}")
        return jsonify({"error": "User has no data in the period"}), 404

    assert len(messages_by_sender) == 1, f"Expected only one sender got {messages_by_sender.keys()} {name}"
    user_messages = list(messages_by_sender.values())[0]

    words_counter = Counter()
    for msg in user_messages:
        if not msg.message:
            continue
        words = msg.message.split()
        for word in words:
            # filter noise like punctuation or 1-character digits
            w = word.strip(string.punctuation).lower()
            if w.isdigit():
                continue
            if w.lower() in COMMON_WORDS_FOR_USER_STATS:
                continue
            words_counter[w] += 1

    most_spoken_words = words_counter.most_common(30)

    # -------------------------------
    # 2️⃣ MESSAGES PER HOUR OF DAY
    # -------------------------------
    hour_counts = [0] * 24
    for msg in user_messages:
        if hasattr(msg, "datetime") and msg.datetime:
            hour_counts[msg.datetime.hour] += 1
    per_hour = {
        "labels": [f"{h % 12 or 12}{'a' if h < 12 else 'p'}" for h in range(24)],
        "values": hour_counts
    }

    # -------------------------------
    # 3️⃣ MESSAGES PER DAY OF WEEK
    # -------------------------------
    weekday_counts = [0] * 7  # Mon=0
    for msg in user_messages:
        if hasattr(msg, "datetime") and msg.datetime:
            weekday_counts[msg.datetime.weekday()] += 1
    per_weekday = {
        "labels": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        "values": weekday_counts
    }

    # -------------------------------
    # 4️⃣ MESSAGES PER WEEK (IN PERIOD)
    # -------------------------------
    week_counts = defaultdict(int)
    for msg in user_messages:
        if hasattr(msg, "datetime") and msg.datetime:
            week_key = msg.datetime.isocalendar()[1]  # week number
            week_counts[week_key] += 1

    sorted_weeks = sorted(week_counts.items())
    per_week = {
        "labels": [f"Week {wk}" for wk, _ in sorted_weeks],
        "values": [cnt for _, cnt in sorted_weeks]
    }

    return add_caching_to_response(jsonify({
        "words": most_spoken_words,
        "per_hour": per_hour,
        "per_weekday": per_weekday,
        "per_week": per_week
    }), 3600, 30)

@app.route('/user/dp/<name>')
async def user_dp(name):
    dp_path = await get_user_dp(name, use_regex=False)
    if not dp_path:
        possible_file_path = f'data/dp/{name}'
        if os.path.exists(possible_file_path):
            dp_path = possible_file_path
        else:
            dp_path = await get_user_dp(name, use_regex=True)
            if not dp_path:
                return add_caching_to_response(("Display picture not found", 404), 60, 30)

    return add_caching_to_response(send_file(dp_path), 86400)


@app.route('/user/admin')
async def user_admin():
    user_profile = await get_user_profile_from_name(USER)
    if not user_profile:
        return jsonify({"error": "User not found"}), 404

    return add_caching_to_response(jsonify(user_profile))

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
    response = make_response(asset)
    response.headers['Content-Type'] = mime_type
    # with open('test_image.webp', 'wb') as f:
    #     f.write(asset)
    return add_caching_to_response(response, 86400, 15)


@app.route('/available_providers')
async def get_available_providers():
    return add_caching_to_response([(provider_name, instance.get_logo()) for provider_name, instance in
            MemoryAggregator.get_instance().providers.items() if
                                    instance.is_working()], 10)

if __name__ == '__main__':
    app.run(debug=True)