import os
import urllib.request, json 

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")
    
# Helper function that returns dictionary of symbol:shares currently held
def whatDoIOwn():
    userID = session["user_id"]
    
    # makes list of dictionaries containing all user's distinct stock symbols
    symbolDictList = db.execute("SELECT DISTINCT symbol FROM stocks WHERE user_id = :userID", userID=userID)
    
    if not symbolDictList:
        return {}
    # converts symbolDictList to list of all symbols
    symbolList = [symbol['symbol'] for symbol in symbolDictList]
    
    # builds a dictionary matching symbols to total number of shares 
    shareSummary = {}
    for s in symbolList:
        totalShares = 0
        for d in db.execute("SELECT * FROM stocks WHERE user_id = :userID", userID=userID):
            if d['symbol'] == s:
                totalShares += d['shares']
        shareSummary.update({s:totalShares})

        # same as shareSummary but with only non-zero shares
        activeShareSummary = {s: ts for s, ts in shareSummary.items() if ts != 0}
    print(activeShareSummary)
    return activeShareSummary    
    

@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    userID = session["user_id"]
    
    # create dictionary of symbol:shares
    activeShareSummary = whatDoIOwn()
    
    finalStockList = []
    # check to make sure activeShareSummary is not empty
    if activeShareSummary:
        # converts it to a list of symbols
        activeSymbols = list(activeShareSummary.keys())

        # builds list of dictionaries containing all stock information displayed on index table
        i=0
        for s in activeSymbols:
            finalStockList.append(lookup(s))
            finalStockList[i].update({'shares':activeShareSummary[s]})
            total = activeShareSummary[s] * finalStockList[i]['price']
            finalStockList[i].update({'total':total})
            i += 1

    cash = db.execute("SELECT cash FROM users WHERE id = :userID", userID=userID)
    actualCash = cash[0]['cash']
    
    # calculates total value of cash + shares
    grandTotal = actualCash
    if activeShareSummary:
        for s in finalStockList:
            grandTotal += s['total']
    
    return render_template("index.html", actualCash=actualCash, finalStockList=finalStockList, grandTotal=grandTotal)

@app.route("/addcash", methods=["GET", "POST"])
@login_required
def addCash():
    """Allows user to add additional cash to their account"""
    if request.method == "GET":
        return render_template("addcash.html")
    if request.method == "POST":
        userID = session["user_id"]
        cash = db.execute("SELECT cash FROM users WHERE id = :userID", userID=userID)
        actualCash = cash[0]['cash']
        
        # throw error if amount is negative
        if int(request.form.get("addcash")) <= 0:
            return apology("Please enter a valid amount.", 403)
        
        # updates user's cash balance in database
        addedCash = int(request.form.get("addcash"))
        newCash = actualCash + addedCash
        db.execute("UPDATE users SET cash = :newCash WHERE id = :userID", newCash=newCash, userID=userID)
        
        return redirect("/")
        
@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "GET":
        return render_template("buy.html")
    if request.method == "POST":
        # return dictionary of symbol, name, and price
        symbolDict = lookup(request.form.get("symbol"))
        
        # checks to make sure symbol is valid
        if symbolDict == None:
            return apology("You must enter a valid symbol.", 403)
        if not request.form.get("shares"):
            return apology("Please enter a positive number of shares.", 403)
        
        # checks to make sure shares is a positive integer
        if int(request.form.get("shares")) <= 0:
            return apology("Please enter a positive number of shares.", 403)
        
        # stores dictionary info in variables
        symbol = symbolDict['symbol']
        price = symbolDict['price']
        shares = int(request.form.get("shares"))
        totalCost = price * shares
        
        userID = session["user_id"]
        
        cash = db.execute("SELECT cash FROM users WHERE id = :userID", userID=userID)
        actualCash = cash[0]['cash']
        
        # checks to make sure user has sufficient funds for purchase
        if totalCost > actualCash:
            return apology("You have insufficient funds for this purchase.", 403)
        else:
            # inserts purchase info into stocks database
            db.execute("INSERT INTO stocks (user_id, symbol, shares) VALUES(:userID, :symbol, :shares)", userID=userID, symbol=symbol, shares=shares)

        # updates user's cash balance
        newCash = actualCash - totalCost
        db.execute("UPDATE users SET cash = :newCash WHERE id = :userID", newCash=newCash, userID=userID)
        
        # flashes message that stocks were purchased
        flash(f"You successfully bought {shares} share(s) of {symbol}!")
        
        return redirect("/")
        

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
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

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
    if request.method == "POST":
        # returns dictionary containing symbol, name, and price
        symbolDict = lookup(request.form.get("symbol"))
        
        # checks to make sure symbol is valid
        if symbolDict == None:
            return apology("No such symbol exists. Try again.", 403)
        else:
            # builds string to display when symbol is found
            quoteText = ""
            quoteText += "A share of {} ({}) costs ".format(symbolDict["name"], symbolDict["symbol"]) + usd(symbolDict["price"])
            
            return render_template("quoted.html", quoteText=quoteText)

@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "GET":
        return render_template("register.html")
    else:
        password = request.form.get("password")
        
        # checks to make sure username was entered
        if not request.form.get("username"):
            return apology("You must enter a username")
        
        # checks to make sure password is valid: must be at least 8 characters and must contain
        # at least one special character
        if not password:
            return apology("You must enter a password.")
        if len(password) < 8:
            return apology("Your password must be at least 8 characters long.")
        if "@" not in password and "#" not in password and "$" not in password \
        and "%" not in password and "^" not in password and "*" not in password and "!" not in password:
            return apology("Your password must include at least one of the special characters.")
        
        # checks to make sure confirmation matches password
        if not request.form.get("confirmation"):
            return apology("You must confirm your password.")
        if request.form.get("password") != request.form.get("confirmation"):
            return apology("Your passwords must match.")
        
        usernames = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))
        
        # checks to make sure username is unique
        if len(usernames) != 0:
            return apology("That username is already taken.")
        
        # inserts username into database and stores password as a hash
        db.execute("INSERT INTO users (username, hash) VALUES(:username, :hash)", username=request.form.get("username"), hash=generate_password_hash(request.form.get("password")))
        
        return redirect("/")

    
@app.route("/sellSelectionMade")
@login_required
def sellSelectionMade():
    """tells users how many shares of selected symbol are available to sell"""
    # stores queried symbol in q
    q = request.args.get("q")
    
    # returns dictionary of symbol:shares with all non-zero shares
    activeShareSummary = whatDoIOwn()
    
    # creates message displaying the number of available shares of q
    message = f"You currently own {activeShareSummary[q]} share(s) of {q}."
    
    return render_template("sellSelectionMade.html", message=message)
    
@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    userID = session["user_id"]
    
    # returns dictionary of symbol:shares with all non-zero shares
    activeShareSummary = whatDoIOwn()
   
    # makes list of symbols from activeShareSummary
    activeSymbols = list(activeShareSummary.keys())
        
    if request.method == "GET":
        return render_template("sell.html", activeSymbols=activeSymbols)
    else:
        selectedSymb = request.form.get("symbol")
        
        # checks to make sure symbol is selected
        if selectedSymb == None:
            return apology("You must select a symbol.", 403)
        
        # checks to make sure shares is valid
        if not request.form.get("shares"):
            return apology("Please enter a positive number of shares.", 403)
        if int(request.form.get("shares")) <= 0:
            return apology("Please enter a positive number of shares.", 403)
        
        shares = int(request.form.get("shares"))
        
        # checks to make sure user has that many shares to sell
        if int(shares) > activeShareSummary[selectedSymb]:
            return apology("You do not own that many shares of {}".format(selectedSymb), 403)
        
        # inserts new transaction into stocks database with negative number of shares
        db.execute("INSERT INTO stocks (user_id, symbol, shares) VALUES(:userID, :symbol, :shares)", userID=userID, symbol=selectedSymb, shares=-shares)
        
        # defines variables for for stock price and user's cash balance
        price = lookup(selectedSymb)['price']
        totalCost = price * shares
        cash = db.execute("SELECT cash FROM users WHERE id = :userID", userID=userID)
        actualCash = cash[0]['cash']
        
        # updates cash
        newCash = actualCash + totalCost
        db.execute("UPDATE users SET cash = :newCash WHERE id = :userID", newCash=newCash, userID=userID)
        
        # flashes message that stocks were sold
        flash(f"You successfully sold {shares} share(s) of {selectedSymb}!")
        
        return redirect("/")

def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
