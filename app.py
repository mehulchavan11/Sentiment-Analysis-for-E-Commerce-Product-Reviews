from flask import Flask, render_template, request
from playwright.sync_api import sync_playwright
import pandas as pd
import nltk
from nltk.sentiment.vader import SentimentIntensityAnalyzer
from sklearn.metrics import confusion_matrix, accuracy_score
import plotly.express as px
import plotly.graph_objects as go
from wordcloud import WordCloud
import matplotlib.pyplot as plt
import os

nltk.download('vader_lexicon')

app = Flask(__name__)

def scrape_flipkart_reviews(url):
    reviews = []
    average_rating = "N/A"
    product_name = "Unknown Product"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url)

        try:
            average_rating = page.locator('div.ipqd2A').first.text_content().strip()
        except:
            pass

        try:
            product_name = page.locator('div.Vu3-9u.eCtPz5').first.text_content().strip()
        except:
            pass

        product_name_written = False
        average_rating_written = False
        page_num = 1

        while True:
            paged_url = f"{url}&page={page_num}"
            page.goto(paged_url)
            page.wait_for_timeout(2000)

            blocks = page.locator('div.col.EPCmJX.Ma1fCG')
            count = blocks.count()
            if count == 0:
                break

            for i in range(count):
                try:
                    rating = blocks.nth(i).locator('div.XQDdHH.Ga3i8K').text_content().strip()
                except:
                    rating = "NA"
                try:
                    title = blocks.nth(i).locator('p.z9E0IG').text_content().strip()
                except:
                    title = "NA"
                try:
                    review = blocks.nth(i).locator('div.ZmyHeo > div > div').text_content().strip()
                except:
                    review = "NA"

                reviews.append({
                    "Product Name": product_name if not product_name_written else "",
                    "Average Rating": average_rating if not average_rating_written else "",
                    "User Rating": rating,
                    "Title": title,
                    "Review": review
                })

                product_name_written = True
                average_rating_written = True

            page_num += 1
        browser.close()

    df = pd.DataFrame(reviews)
    df.to_csv("flipkart_reviews.csv", index=False)
    return df, product_name

def analyze_sentiment(df):
    sid = SentimentIntensityAnalyzer()
    df["compound"] = df["Review"].apply(lambda x: sid.polarity_scores(x)["compound"])
    color_map = {
        1: "#ff4d4d",  # red
        2: "#ff944d",  # orange
        3: "#ffd11a",  # yellow
        4: "#7cd67c",  # green
        5: "#4d79ff"  # blue
    }

    def compound_to_star(comp):
        
        if comp <= -0.6:
            return 1
        elif comp <= 0.2:
            return 2
        elif comp <= 0.2:
            return 3
        elif comp <= 0.6:
            return 4
        else:
            return 5

    df["Predicted Rating"] = df["compound"].apply(compound_to_star)
    df["User Rating"] = pd.to_numeric(df["User Rating"], errors="coerce")
    df.dropna(subset=["User Rating"], inplace=True)
    df["User Rating"] = df["User Rating"].astype(int)

    
    if len(df) > 0:
        acc = accuracy_score(df["User Rating"], df["Predicted Rating"])
        accuracy_percent = round(acc * 100, 2)
    else:
        accuracy_percent = 0.0

    os.makedirs("static", exist_ok=True)

    def save_wordcloud(subset, filename):
        if subset.empty:
            return
        text = " ".join(subset["Review"])
        wc = WordCloud(width=800, height=400, background_color="white").generate(text)
        plt.figure(figsize=(10, 5))
        plt.imshow(wc, interpolation="bilinear")
        plt.axis("off")
        plt.tight_layout()
        plt.savefig(os.path.join("static", filename))
        plt.close()

    save_wordcloud(df[df["Predicted Rating"] <= 2], "neg_wc.png")
    save_wordcloud(df[df["Predicted Rating"] == 3], "avg_wc.png")
    save_wordcloud(df[df["Predicted Rating"] >= 4], "pos_wc.png")

    pie_actual = px.pie(
        df,
        names="User Rating",
        title="Actual Ratings",
        color="User Rating",
        color_discrete_map=color_map
    ).to_html(full_html=False)

    pie_pred = px.pie(
        df,
        names="Predicted Rating",
        title="Predicted Ratings",
        color="Predicted Rating",
        color_discrete_map=color_map
    ).to_html(full_html=False)

    hist_actual = px.histogram(df, x="User Rating", title="Actual Ratings Histogram").to_html(full_html=False)
    hist_pred = px.histogram(df, x="Predicted Rating", title="Predicted Ratings Histogram").to_html(full_html=False)

    cm = confusion_matrix(df["User Rating"], df["Predicted Rating"], labels=[1, 2, 3, 4, 5])
    cm_fig = go.Figure(data=go.Heatmap(
        z=cm, x=[1, 2, 3, 4, 5], y=[1, 2, 3, 4, 5], colorscale="Viridis"))
    cm_fig.update_layout(title="Confusion Matrix", xaxis_title="Predicted", yaxis_title="Actual")
    cm_html = cm_fig.to_html(full_html=False)

    return {
        "pie_actual": pie_actual,
        "pie_pred": pie_pred,
        "hist_actual": hist_actual,
        "hist_pred": hist_pred,
        "conf_matrix": cm_html,
        "wordclouds": ["neg_wc.png", "avg_wc.png", "pos_wc.png"],
        "accuracy": accuracy_percent,
    }

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        url = request.form.get("flipkart_url")
        if url:
            df, product_name = scrape_flipkart_reviews(url)
            result = analyze_sentiment(df)
            return render_template("analysis.html", product_name=product_name, **result)
    return render_template("index.html")

if __name__ == "__main__":
    app.run(debug=True)
