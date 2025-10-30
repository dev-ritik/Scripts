import asyncio
import string
from collections import defaultdict, Counter

import configs
import init
from configs import COMMON_WORDS_FOR_USER_STATS, USER

# This should be the first line in the file. It initializes the app.
init.init()

import mimetypes

import aiofiles

from datetime import datetime, timedelta

from flask import Flask, render_template, request, send_file, make_response, jsonify

from common import get_user_dp, MemoryAggregator, get_profile_json, get_user_profile_from_name

app = Flask(__name__)


@app.route('/', methods=['GET'])
async def index():
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


@app.route('/chat_data')
async def chat_data():
    on_date_str = request.args.get('date')
    seek_days = int(request.args.get('seek_days', 0))
    group = request.args.get('group', 'true') == 'true'
    providers_param = request.args.get('providers')  # comma-separated list
    sender_regex = request.args.get('sender_regex')

    if not on_date_str:
        return 'Invalid date format', 400

    seek_days = 0 if seek_days < 0 else seek_days
    try:
        on_date = datetime.strptime(on_date_str, "%Y-%m-%d").date()
    except ValueError:
        return "Invalid date format", 400

    providers = [p.strip() for p in providers_param.split(",") if p.strip()] if providers_param else None

    events = await MemoryAggregator.get_events_for_dates(on_date - timedelta(days=seek_days),
                                                         on_date + timedelta(days=seek_days),
                                                         ignore_groups=not group,
                                                         providers=providers, sender_regex=sender_regex)

    events.sort(key=lambda x: x.datetime)

    return jsonify([event.to_dict() for event in events])


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


@app.route("/circles")
def circles_page():
    return render_template("circles.html")


@app.route("/circle_data")
async def circle_data():
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")

    start_date = datetime.strptime(start_date, "%Y-%m-%d").date() if start_date else None
    end_date = datetime.strptime(end_date, "%Y-%m-%d").date() if end_date else None

    if not start_date or not end_date or end_date < start_date:
        print(start_date, end_date)
        return f"Invalid date format {start_date} {end_date}", 400

    messages_by_sender = await MemoryAggregator.get_instance().get_messages_by_sender(start_date, end_date,
                                                                                      ignore_groups=True)
    del messages_by_sender[configs.USER]

    message_count_by_sender = {}
    for sender, messages in messages_by_sender.items():
        message_count_by_sender[sender] = len(messages)
        words_counter = defaultdict(int)
        for message in messages:
            if message.message:
                words = message.message.split()
                for word in words:
                    if len(word) == 1 and (word.isdigit() or word in string.punctuation):
                        continue
                    words_counter[word] += 1

    # Get the top 15 most active people
    top_15_people = sorted(message_count_by_sender.items(), key=lambda x: x[1], reverse=True)[:15]

    people = []
    for top_people in top_15_people:
        people.append({
            "name": top_people[0],
            "dp": f"/user/dp/{top_people[0]}",
            "chats": top_people[1],
        })

    return jsonify({"people": people})


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

    user_regex = user_profile.get('name_regex')
    messages_by_sender = await MemoryAggregator.get_instance().get_messages_by_sender(start_date, end_date,
                                                                                      ignore_groups=True,
                                                                                      sender_regex=user_regex)

    if not messages_by_sender:
        return jsonify({"error": "User has no data in the period"}), 404

    assert len(messages_by_sender) == 1, f"Expected only one sender got {messages_by_sender.keys()} {user_regex}"
    user_messages = list(messages_by_sender.values())[0]

    words_counter = Counter()
    for msg in user_messages:
        if not msg.message:
            continue
        words = msg.message.split()
        for word in words:
            # filter noise like punctuation or 1-character digits
            w = word.strip(string.punctuation).lower()
            if len(w) <= 1 or w.isdigit():
                continue
            if w.lower() in COMMON_WORDS_FOR_USER_STATS:
                continue
            words_counter[w] += 1

    most_spoken_words = words_counter.most_common(18)

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

    return jsonify({
        "words": most_spoken_words,
        "per_hour": per_hour,
        "per_weekday": per_weekday,
        "per_week": per_week
    }), 200

@app.route('/user/dp/<name>')
async def user_dp(name):
    dp_path = await get_user_dp(name)
    if not dp_path:
        return "Display picture not found", 404

    response = make_response(send_file(dp_path))
    # Cache for 24 hours
    response.headers['Cache-Control'] = 'public, max-age=86400'
    return response


@app.route('/user/admin')
async def user_admin():
    user_profile = await get_user_profile_from_name(USER)
    if not user_profile:
        return jsonify({"error": "User not found"}), 404

    return jsonify(user_profile), 200

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