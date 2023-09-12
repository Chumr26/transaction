import os

from cs50 import SQL
from datetime import datetime
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd, valid_password

# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/", methods=["GET"])
@login_required
def index():
    """Show portfolio of stocks"""
    # Get username
    user = db.execute("SELECT * FROM users WHERE id = ?", session["user_id"])
    username = user[0]["username"]
    # Get history of user
    history = db.execute("SELECT symbol,SUM(shares) AS shares FROM history WHERE username = ? GROUP BY symbol", username)
    # Creat a list of dicts
    stocks = []
    stock_total = 0
    for i in history:
        stock = i["symbol"]
        shares = i["shares"]
        if shares == 0:
            continue
        current_price = lookup(stock)["price"]
        total_value = current_price * shares
        stock_total += total_value
        stocks.append({
            "symbol": stock,
            "name": lookup(stock)["name"],
            "shares": shares,
            "current_price": usd(current_price),
            "total_value": usd(total_value)
        })
    # Balance
    cash_balance = user[0]["cash"]
    grand_total = cash_balance + stock_total
    # Return
    return render_template("index.html", stocks=stocks, cash_balance=usd(cash_balance), grand_total=usd(grand_total))


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    # Get method
    if request.method == "GET":
        return render_template("buy.html")
    # Post method
    else:
        # Validate symbol
        symbol = request.form.get("symbol")
        if not symbol:
            return apology("symbol isn't provided")
        dict = lookup(symbol)
        if not dict:
            return apology("symbol doesn't match")
        # Validate shares
        shares = request.form.get("shares")
        try:
            shares = int(shares)
        except ValueError:
            return apology("shares must be positive integer")

        if shares < 0:
            return apology("shares must be positive integer")
        # Validate cash
        user = db.execute("SELECT * FROM users WHERE id = ?", session["user_id"])
        cash = user[0]["cash"]
        price = dict["price"]
        if cash < (price * shares):
            return apology("not enough cash")
        # Update cash
        remain_cash = cash - (price * shares)
        db.execute("UPDATE users SET cash = ? WHERE id = ?", remain_cash, session["user_id"])
        # Insert into history
        time = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        db.execute("INSERT INTO history (username, status, symbol, price, shares, time) VALUES (?, ?, ?, ?, ?, ?)",user[0]["username"], "buy", symbol.upper(), price, shares, time)
        # Redirect users to home page
        flash("Bought!")
        return redirect("/")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    user = db.execute("SELECT * FROM users WHERE id = ?", session["user_id"])
    username = user[0]["username"]
    history = db.execute("SELECT status, symbol, price, shares, time FROM history WHERE username = ?", username)
    return render_template("history.html", history=history)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "GET":
        return render_template("quote.html")
    else:
        symbol = request.form.get("symbol")
        dict = lookup(symbol)
        if not dict:
            return apology("Invalid symbol")
        return render_template("quoted.html", dict=dict)


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "GET":
        return render_template("register.html")
    else:
        # Get data from the submited register form
        username = request.form.get("username")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")
        # Select all user already exists
        exists_users = db.execute("SELECT username FROM users;")
        # Validate username
        if not username:
            return apology("Username mustn't blank!")
        for exists_user in exists_users:
            if username == exists_user["username"]:
                return apology("Username already exists!")
        # Validate password
        if not password:
            return apology("Password mustn't blank!")
        if password != confirmation:
            return apology("Password and confirmation don't match!")
        if not valid_password(password):
            return apology("Password must contain number, uppercase, lowercase and 8 characters long")
        # Insert new user into database
        hash = generate_password_hash(password)
        db.execute("INSERT INTO users (username, hash) VALUES (?, ?)", username, hash)
        flash("Registered!")
        return redirect("/login")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    user = db.execute("SELECT * FROM users WHERE id = ?", session["user_id"])
    username = user[0]["username"]
    symbols = db.execute("SELECT symbol,SUM(shares) AS shares FROM history WHERE username = ? GROUP BY symbol", username)
    if request.method == "GET":
        return render_template("sell.html", symbols=symbols)
    else:
        owned_stock = {}
        for i in symbols:
            owned_stock[i["symbol"]] = i["shares"]
        symbol = request.form.get("symbol")
        shares = request.form.get("shares")
        if not symbol:
            return apology("sympol mustn't blank")
        if symbol not in owned_stock:
            return apology("stock ist'n owned")
        if not shares:
            return apology("shares mustn't blank")
        try:
            shares = int(shares)
        except ValueError:
            return apology("shares must be numberic")
        if shares <= 0:
            return apology("shares must be positive")
        if shares > owned_stock[symbol]:
            return apology("not enough shares")
        # Update cash
        cash = user[0]["cash"]
        price = lookup(symbol)["price"]
        remain_cash = cash + (price * shares)
        db.execute("UPDATE users SET cash = ? WHERE id = ?", remain_cash, session["user_id"])
        # Insert into history
        time = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        db.execute("INSERT INTO history (username, status, symbol, price, shares, time) VALUES (?, ?, ?, ?, ?, ?)", username, "sell", symbol, price, shares * (-1), time)
        # Redirect users to home page
        flash("Sold!")
        return redirect("/")


@app.route("/account")
@login_required
def account():
    user = db.execute("SELECT * FROM users WHERE id = ?", session["user_id"])
    username = user[0]["username"]
    cash = user[0]["cash"]
    return render_template("account.html", username=username, cash=usd(cash))


@app.route("/password", methods=["POST"])
@login_required
def password():
    user = db.execute("SELECT * FROM users WHERE id = ?", session["user_id"])
    old_password = request.form.get("old_password")
    new_password = request.form.get("new_password")
    confirmation = request.form.get("confirmation")
    if not old_password or not new_password or not confirmation:
        return apology("input boxs mustn't blank")
    if not check_password_hash(user[0]["hash"], old_password):
        return apology("old password doesn't match")
    if new_password != confirmation:
        return apology("new password doesn't match")
    if not valid_password(new_password):
        return apology("Password must contain number, uppercase, lowercase and 8 characters long")
    hash = generate_password_hash(new_password)
    db.execute("UPDATE users SET hash = ? WHERE id = ?", hash, user[0]["id"])
    flash("Changed!")
    return redirect("/")


@app.route("/cash", methods=["POST"])
@login_required
def cash():
    cash = request.form.get("cash")
    if not cash:
        return apology("input boxs mustn't blank")
    try:
        cash = int(cash)
    except ValueError:
        return apology("cash boxs must be integer")
    if cash < 0:
        return apology("cash boxs must be positive")
    db.execute("UPDATE users SET cash = ? WHERE id = ?", cash, session["user_id"])
    return redirect("/account")