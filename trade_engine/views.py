from django.shortcuts import render
import pandas as pd
from plotly.offline import plot
import plotly.express as px


def index(request):
    df = pd.DataFrame({"x": range(10), "y": range(10)})
    fig = px.line(df, x="x", y="x")
    #fig.update_yaxes(autorange="reversed")
    gantt_plot = plot(fig, output_type="div")
    context = {'plot_div': gantt_plot}
    return render(request, 'trade_engine/index.html', context)
