import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from pymongo import MongoClient
import numpy as np

# ─── Page Config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Airbnb Explorer",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Sans:wght@300;400;500;600&display=swap');

  html, body, [class*="css"] {
    font-family: 'DM Sans', sans-serif;
  }
  h1, h2, h3 {
    font-family: 'DM Serif Display', serif;
  }
  .main { background-color: #faf9f6; }

  .metric-card {
    background: white;
    border-radius: 16px;
    padding: 1.4rem 1.6rem;
    box-shadow: 0 2px 12px rgba(0,0,0,0.06);
    border-left: 4px solid #FF5A5F;
    margin-bottom: 0.5rem;
  }
  .metric-card h2 { color: #FF5A5F; margin: 0; font-size: 2rem; }
  .metric-card p  { color: #888; margin: 0; font-size: 0.85rem; letter-spacing: 0.04em; text-transform: uppercase; }

  .section-header {
    font-family: 'DM Serif Display', serif;
    font-size: 1.5rem;
    color: #222;
    margin-top: 2rem;
    margin-bottom: 0.5rem;
    border-bottom: 2px solid #FF5A5F;
    padding-bottom: 0.3rem;
  }
  .stSelectbox label, .stSlider label, .stMultiSelect label {
    font-weight: 500;
    color: #444;
  }
</style>
""", unsafe_allow_html=True)

# ─── MongoDB Connection (uses Streamlit Secrets) ───────────────────────────────
@st.cache_resource
def get_client():
    # Reads from .streamlit/secrets.toml  →  [mongo] uri = "mongodb+srv://..."
    uri = st.secrets["mongo"]["uri"]
    return MongoClient(uri)

@st.cache_data(ttl=600)
def load_data():
    client = get_client()
    db     = client["sample_airbnb"]
    col    = db["listingsAndReviews"]

    fields = {
        "name": 1, "property_type": 1, "room_type": 1,
        "bedrooms": 1, "bathrooms": 1, "beds": 1,
        "price": 1, "cleaning_fee": 1,
        "number_of_reviews": 1, "review_scores.review_scores_rating": 1,
        "address.country": 1, "address.market": 1,
        "amenities": 1, "host.host_name": 1,
        "accommodates": 1, "minimum_nights": 1,
    }

    docs = list(col.find({}, fields).limit(5000))
    df   = pd.json_normalize(docs)

    # ── clean columns ──
    rename = {
        "address.country":                     "country",
        "address.market":                      "market",
        "review_scores.review_scores_rating":  "rating",
        "host.host_name":                      "host_name",
    }
    df.rename(columns=rename, inplace=True)

    # price / cleaning_fee come as bson.Decimal128 → float
    for col_name in ["price", "cleaning_fee"]:
        if col_name in df.columns:
            df[col_name] = df[col_name].apply(
                lambda x: float(str(x)) if x is not None else np.nan
            )

    df["rating"]   = pd.to_numeric(df.get("rating"),   errors="coerce")
    df["bedrooms"] = pd.to_numeric(df.get("bedrooms"), errors="coerce")
    df["beds"]     = pd.to_numeric(df.get("beds"),     errors="coerce")
    df["amenity_count"] = df["amenities"].apply(lambda x: len(x) if isinstance(x, list) else 0)

    return df

# ─── Load ──────────────────────────────────────────────────────────────────────
with st.spinner("Connecting to MongoDB…"):
    df = load_data()

# ─── Header ───────────────────────────────────────────────────────────────────
st.markdown("""
<div style='display:flex;align-items:center;gap:12px;margin-bottom:0.2rem'>
  <span style='font-size:2.8rem'>🏠</span>
  <div>
    <h1 style='margin:0;font-family:DM Serif Display,serif;font-size:2.4rem;color:#222'>
      Airbnb Explorer
    </h1>
    <p style='margin:0;color:#888;font-size:0.95rem'>
      Interactive dashboard · sample_airbnb · MongoDB
    </p>
  </div>
</div>
""", unsafe_allow_html=True)

st.markdown("---")

# ─── Sidebar Filters ──────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🔍 Filters")

    countries = sorted(df["country"].dropna().unique().tolist())
    sel_countries = st.multiselect("Country", countries, default=[])

    prop_types = sorted(df["property_type"].dropna().unique().tolist())
    sel_props = st.multiselect("Property Type", prop_types, default=[])

    price_min, price_max = 0, int(df["price"].dropna().quantile(0.97))
    price_range = st.slider("Price per Night (USD)", price_min, price_max, (price_min, price_max))

    min_rating = st.slider("Minimum Rating", 0, 100, 60)

    st.markdown("---")
    st.caption("Data: MongoDB · sample_airbnb")

# ─── Filter DataFrame ─────────────────────────────────────────────────────────
mask = pd.Series([True] * len(df))
if sel_countries:
    mask &= df["country"].isin(sel_countries)
if sel_props:
    mask &= df["property_type"].isin(sel_props)
mask &= df["price"].between(price_range[0], price_range[1])
mask &= (df["rating"] >= min_rating) | df["rating"].isna()
fdf = df[mask]

# ─── KPI Cards ────────────────────────────────────────────────────────────────
c1, c2, c3, c4 = st.columns(4)
def kpi(col, value, label):
    col.markdown(f"""
    <div class='metric-card'>
      <p>{label}</p>
      <h2>{value}</h2>
    </div>""", unsafe_allow_html=True)

kpi(c1, f"{len(fdf):,}",                                    "Total Listings")
kpi(c2, f"${fdf['price'].median():,.0f}",                   "Median Price / Night")
kpi(c3, f"{fdf['rating'].mean():.1f} / 100",                "Avg Rating")
kpi(c4, f"{fdf['number_of_reviews'].sum():,.0f}",           "Total Reviews")

# ─── Row 1: Price Distribution + Room Type ────────────────────────────────────
st.markdown("<div class='section-header'>Price & Room Type</div>", unsafe_allow_html=True)
r1a, r1b = st.columns([2, 1])

with r1a:
    fig_price = px.histogram(
        fdf[fdf["price"] <= price_range[1]], x="price", nbins=60,
        color_discrete_sequence=["#FF5A5F"],
        labels={"price": "Price (USD)", "count": "Listings"},
        title="Price Distribution"
    )
    fig_price.update_layout(
        plot_bgcolor="white", paper_bgcolor="white",
        margin=dict(t=40, b=20, l=0, r=0), showlegend=False
    )
    st.plotly_chart(fig_price, use_container_width=True)

with r1b:
    room_counts = fdf["room_type"].value_counts().reset_index()
    room_counts.columns = ["room_type", "count"]
    fig_room = px.pie(
        room_counts, values="count", names="room_type",
        color_discrete_sequence=["#FF5A5F","#FC642D","#FFB400","#008489"],
        title="Room Type Split", hole=0.45
    )
    fig_room.update_layout(margin=dict(t=40, b=20), paper_bgcolor="white")
    st.plotly_chart(fig_room, use_container_width=True)

# ─── Row 2: Top Markets + Avg Price by Property Type ──────────────────────────
st.markdown("<div class='section-header'>Markets & Property Types</div>", unsafe_allow_html=True)
r2a, r2b = st.columns(2)

with r2a:
    top_markets = (
        fdf.groupby("market")["price"]
        .median().dropna().sort_values(ascending=False).head(12).reset_index()
    )
    fig_mkt = px.bar(
        top_markets, x="price", y="market", orientation="h",
        color="price", color_continuous_scale="RdYlGn_r",
        labels={"price": "Median Price (USD)", "market": ""},
        title="Top 12 Markets by Median Price"
    )
    fig_mkt.update_layout(
        plot_bgcolor="white", paper_bgcolor="white",
        coloraxis_showscale=False, margin=dict(t=40, b=20, l=0, r=0)
    )
    st.plotly_chart(fig_mkt, use_container_width=True)

with r2b:
    prop_price = (
        fdf.groupby("property_type")["price"]
        .median().dropna().sort_values(ascending=False).head(10).reset_index()
    )
    fig_prop = px.bar(
        prop_price, x="property_type", y="price",
        color_discrete_sequence=["#008489"],
        labels={"property_type": "", "price": "Median Price (USD)"},
        title="Median Price by Property Type (Top 10)"
    )
    fig_prop.update_layout(
        plot_bgcolor="white", paper_bgcolor="white",
        xaxis_tickangle=-35, margin=dict(t=40, b=60, l=0, r=0)
    )
    st.plotly_chart(fig_prop, use_container_width=True)

# ─── Row 3: Rating vs Price scatter + Amenities ───────────────────────────────
st.markdown("<div class='section-header'>Ratings & Amenities</div>", unsafe_allow_html=True)
r3a, r3b = st.columns([2, 1])

with r3a:
    scatter_df = fdf.dropna(subset=["price", "rating"]).sample(min(1500, len(fdf)))
    fig_scatter = px.scatter(
        scatter_df, x="price", y="rating",
        color="room_type", opacity=0.6, size_max=8,
        color_discrete_sequence=["#FF5A5F","#FC642D","#FFB400","#008489"],
        labels={"price": "Price (USD)", "rating": "Review Score"},
        title="Price vs Rating"
    )
    fig_scatter.update_layout(
        plot_bgcolor="white", paper_bgcolor="white",
        margin=dict(t=40, b=20, l=0, r=0)
    )
    st.plotly_chart(fig_scatter, use_container_width=True)

with r3b:
    fig_amenity = px.histogram(
        fdf, x="amenity_count", nbins=30,
        color_discrete_sequence=["#FFB400"],
        labels={"amenity_count": "# Amenities", "count": "Listings"},
        title="Amenity Count Distribution"
    )
    fig_amenity.update_layout(
        plot_bgcolor="white", paper_bgcolor="white",
        margin=dict(t=40, b=20, l=0, r=0), showlegend=False
    )
    st.plotly_chart(fig_amenity, use_container_width=True)

# ─── Row 4: Country comparison ────────────────────────────────────────────────
st.markdown("<div class='section-header'>Country Comparison</div>", unsafe_allow_html=True)
country_stats = (
    fdf.groupby("country")
    .agg(listings=("name","count"), median_price=("price","median"), avg_rating=("rating","mean"))
    .reset_index().sort_values("listings", ascending=False)
)
fig_country = go.Figure()
fig_country.add_trace(go.Bar(
    x=country_stats["country"], y=country_stats["median_price"],
    name="Median Price", marker_color="#FF5A5F", yaxis="y1"
))
fig_country.add_trace(go.Scatter(
    x=country_stats["country"], y=country_stats["avg_rating"],
    name="Avg Rating", mode="lines+markers",
    marker=dict(color="#008489", size=8), yaxis="y2"
))
fig_country.update_layout(
    yaxis=dict(title="Median Price (USD)"),
    yaxis2=dict(title="Avg Rating", overlaying="y", side="right", range=[50,100]),
    plot_bgcolor="white", paper_bgcolor="white",
    legend=dict(orientation="h", y=1.1),
    margin=dict(t=20, b=20, l=0, r=0)
)
st.plotly_chart(fig_country, use_container_width=True)

# ─── Raw Data Table ───────────────────────────────────────────────────────────
with st.expander("📋 Raw Data (filtered)"):
    show_cols = ["name","country","market","property_type","room_type",
                 "bedrooms","beds","price","rating","number_of_reviews","amenity_count"]
    available = [c for c in show_cols if c in fdf.columns]
    st.dataframe(fdf[available].reset_index(drop=True), use_container_width=True, height=300)

st.markdown("""
<hr style='margin-top:2rem'>
<p style='text-align:center;color:#bbb;font-size:0.8rem'>
  Built with Streamlit · MongoDB · Plotly &nbsp;|&nbsp; sample_airbnb dataset
</p>
""", unsafe_allow_html=True)
