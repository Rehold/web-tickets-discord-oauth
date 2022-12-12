import datetime
import math
import os
import re
import uuid
import timeago as timeago
from PIL import Image
from config import TOKEN, CLIENT_SECRET, MONGO_URI, OAUTH_URL
from flask import Flask, render_template, request, session, redirect, url_for, send_file, Response
from flask_hashing import Hashing
from flask_pymongo import PyMongo
from flask import jsonify
from flask_mail import Mail, Message
import random
from zenora import APIClient
from datetime import timedelta


UNITS = {"s": "seconds", "m": "minutes", "h": "hours", "d": "days", "w": "weeks", "M": "months", "y": "years"}

#get current time as unix
ranks = {
    "admin": {
        "name": "Admin",
        "color": "danger",
    },
    "moderator": {
        "name": "Support",
        "color": "info",
    }

}

def convert_to_timestamp(s):
    count = int(s[:-1])
    unit = UNITS[s[-1]]
    if unit == "months":
        unit = "days"
        td = timedelta(**{unit: count * 30})
    elif unit == "years":
        unit = "days"
        td = timedelta(**{unit: count * 365})
    else:
        td = timedelta(**{unit: count})

    if unit == "months":
        seconds = td.seconds + 60 * 60 * 24 * td.days * 30
    elif unit == "years":
        seconds = td.seconds + 60 * 60 * 24 * td.days * 365
    else:
        seconds = td.seconds + 60 * 60 * 24 * td.days
    currentTime = datetime.datetime.now()
    return round(int((currentTime + timedelta(seconds=seconds)).timestamp()))



app = Flask(__name__)
app.config['SECRET_KEY'] = 'SomeRandomString_325wteajhDSJGHasdg'
app.config["MONGO_URI"] = MONGO_URI
mongo = PyMongo(app)
client = APIClient(TOKEN, client_secret=CLIENT_SECRET)
app.permanent_session_lifetime = timedelta(days=12)

@app.route("/")
def index():
    if 'token' not in session:
        return redirect(url_for('oauth_login'))

    bearer = APIClient(session.get('token'), bearer=True)
    discordUser = bearer.users.get_current_user()
    if discordUser is None:
        session.pop('token', None)
        return redirect(url_for('oauth_login'))

    user = mongo.db.users.find_one({"_id": discordUser.id})

    if user['rank'] != 'admin' and user['rank'] != 'support':
        tickets = mongo.db.tickets.find({"user": discordUser.id})
        dict = {
            "user": user,
            "discordUser": discordUser,
            "tickets": tickets,

        }
    else:
        unAnsweredTickets = mongo.db.tickets.find({"last_update": "user"})
        answeredTickets = mongo.db.tickets.find({"last_update": "staff"})
        dict = {
            "user": user,
            "discordUser": discordUser,
            "unAnsweredTickets": unAnsweredTickets,
            "answeredTickets": answeredTickets,

        }




    return render_template("index.html", dict=dict)



@app.route("/oauth/login")
def oauth_login():
    return redirect(OAUTH_URL)

@app.route("/oauth/callback")
def oauth_callback():
    args = request.args
    if "code" not in args:
        return redirect(url_for('index'))
    code = request.args["code"]
    oauth_response = client.oauth.get_access_token(code, "http://localhost:5000/oauth/callback").access_token
    session['token'] = oauth_response

    bearer = APIClient(session.get('token'), bearer=True)
    discordUser = bearer.users.get_current_user()

    user = mongo.db.users.find_one({"_id": discordUser.id})
    if user is None:
        layout = {
            "rank": "user"
        }
        mongo.db.users.update_one({"_id": discordUser.id}, {"$set": layout}, upsert=True)
    return redirect(url_for('index'))

@app.route("/logout")
def oauth_logout():
    session.pop('token', None)
    return redirect(url_for('index'))


@app.route("/tickets/create")
def create_ticket():
    if 'token' not in session:
        return redirect(url_for('oauth_login'))
    bearer = APIClient(session.get('token'), bearer=True)
    discordUser = bearer.users.get_current_user()
    if discordUser is None:
        session.pop('token', None)
        return redirect(url_for('oauth_login'))
    user = mongo.db.users.find_one({"_id": discordUser.id})

    dict = {
        "user": user,
        "discordUser": discordUser,

    }
    return render_template("create_ticket.html", dict=dict)

@app.route("/tickets/create/validate", methods=['POST'])
def create_ticket_validate():
    if request.method != 'POST':
        return redirect(url_for('index'))
    if 'token' not in session:
        return redirect(url_for('oauth_login'))
    bearer = APIClient(session.get('token'), bearer=True)
    discordUser = bearer.users.get_current_user()
    if discordUser is None:
        session.pop('token', None)
        return redirect(url_for('oauth_login'))
    user = mongo.db.users.find_one({"_id": discordUser.id})



    subject = request.form['subject']
    description = request.form['description']
    layout = {
        "user": discordUser.id,
        "subject": subject,
        "description": description,
        "status": "open",
        "created_at": datetime.datetime.now(),
        "last_update": "user",
        "messages": [],

    }
    ticket_id = mongo.db.data.find_one({"_id": "abc"})
    if ticket_id is None:
        mongo.db.data.update_one({"_id": "abc"}, {"$set": {"ticket_id": 1}}, upsert=True)
        ticket_id = 1
    else:
        ticket_id = ticket_id['ticket_id']
        mongo.db.data.update_one({"_id": "abc"}, {"$set": {"ticket_id": ticket_id + 1}}, upsert=True)

    mongo.db.tickets.update_one({"_id": ticket_id}, {"$set": layout}, upsert=True)
    return redirect(url_for('index'))

@app.route("/tickets/<ticket_id>")
def view_ticket(ticket_id):
    if 'token' not in session:
        return redirect(url_for('oauth_login'))


    bearer = APIClient(session.get('token'), bearer=True)
    discordUser = bearer.users.get_current_user()
    if discordUser is None:
        session.pop('token', None)
        return redirect(url_for('oauth_login'))

    user = mongo.db.users.find_one({"_id": discordUser.id})

    ticket_id = int(ticket_id)
    ticket = mongo.db.tickets.find_one({"_id": ticket_id})

    if ticket is None:
        return redirect(url_for('index'))

    for msg in ticket['messages']:
        msg['user'] = client.users.get_user(msg['user'])
    ticket['user'] = discordUser

    dict = {
        "user": user,
        "discordUser": discordUser,
        "ticket": ticket,
    }
    return render_template("ticket_view.html", dict=dict)

@app.route("/tickets/<ticket_id>/send-message", methods=['POST'])
def send_message(ticket_id):
    if request.method != 'POST':
        return redirect(url_for('index'))
    if 'token' not in session:
        return redirect(url_for('oauth_login'))
    bearer = APIClient(session.get('token'), bearer=True)
    discordUser = bearer.users.get_current_user()
    if discordUser is None:
        session.pop('token', None)
        return redirect(url_for('oauth_login'))
    user = mongo.db.users.find_one({"_id": discordUser.id})

    ticket_id = int(ticket_id)
    ticket = mongo.db.tickets.find_one({"_id": ticket_id})

    if ticket is None:
        return redirect(url_for('index'))

    message = request.form['message']
    layout = {
        "user": discordUser.id,
        "content": message,
        "created_at": datetime.datetime.now(),
    }
    mongo.db.tickets.update_one({"_id": ticket_id}, {"$push": {"messages": layout}}, upsert=True)

    if user['rank'] == "user":
        mongo.db.tickets.update_one({"_id": ticket_id}, {"$set": {"last_update": "user"}}, upsert=True)
    else:
        mongo.db.tickets.update_one({"_id": ticket_id}, {"$set": {"last_update": "staff"}}, upsert=True)

    return redirect(url_for('view_ticket', ticket_id=ticket_id))

@app.route("/tickets/<ticket_id>/close")
def close_ticket(ticket_id):
    if 'token' not in session:
        return redirect(url_for('oauth_login'))
    bearer = APIClient(session.get('token'), bearer=True)
    discordUser = bearer.users.get_current_user()
    if discordUser is None:
        session.pop('token', None)
        return redirect(url_for('oauth_login'))
    user = mongo.db.users.find_one({"_id": discordUser.id})

    ticket_id = int(ticket_id)
    ticket = mongo.db.tickets.find_one({"_id": ticket_id})

    if ticket is None:
        return redirect(url_for('index'))


    mongo.db.tickets.update_one({"_id": ticket_id}, {"$set": {"status": "closed"}}, upsert=True)

    return redirect(url_for('view_ticket', ticket_id=ticket_id))

@app.route("/set-rank")
def set_rank():
    if 'token' not in session:
        return redirect(url_for('oauth_login'))
    bearer = APIClient(session.get('token'), bearer=True)
    discordUser = bearer.users.get_current_user()
    if discordUser is None:
        session.pop('token', None)
        return redirect(url_for('oauth_login'))
    user = mongo.db.users.find_one({"_id": discordUser.id})

    if user['rank'] != "admin":
        return redirect(url_for('index'))

    dict = {
        "user": user,
        "discordUser": discordUser,
    }
    return render_template("set_rank.html", dict=dict)

@app.route("/set-rank/validate", methods=['POST'])
def set_rank_validate():
    if request.method != 'POST':
        return redirect(url_for('index'))
    if 'token' not in session:
        return redirect(url_for('oauth_login'))
    bearer = APIClient(session.get('token'), bearer=True)
    discordUser = bearer.users.get_current_user()
    if discordUser is None:
        session.pop('token', None)
        return redirect(url_for('oauth_login'))
    user = mongo.db.users.find_one({"_id": discordUser.id})

    if user['rank'] != "admin":
        return redirect(url_for('index'))

    discord_id = request.form['discord_id']
    rank = request.form['rank']

    mongo.db.users.update_one({"_id": discord_id}, {"$set": {"rank": rank}}, upsert=True)

    return redirect(url_for('index'))

if __name__ == "__main__":
    app.run(debug=True)

