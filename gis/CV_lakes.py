"""
Name:       CV_lakes.py

Label:      Impute missing values in longitudinal data on ecological status of lakes.

Summary:    ThorNoe.GitHub.io/GreenGDP explains the overall approach and methodology.

Usage:      This is a standalone script that only serves to evaluates the robustness of 
            the imputation method coded up in script_module.py and applied by script.py, 
            which supports WaterbodiesScriptTool in the gis.tbx toolbox.
            See GitHub.com/ThorNoe/GreenGDP for instructions to run or update it all.

License:    MIT Copyright (c) 2024
Author:     Thor Donsby Noe 
"""

########################################################################################
#   0. Functions
########################################################################################
import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import tqdm
from cycler import cycler
from sklearn.experimental import enable_iterative_imputer  # noqa
from sklearn.impute import IterativeImputer
from sklearn.metrics import accuracy_score

# Multivariate imputer using BayesianRidge() estimator with increased tolerance
imputer = IterativeImputer(tol=1e-1, max_iter=1000, random_state=0)

# Color-blind-friendly color scheme for qualitative data by Tol: personal.sron.nl/~pault
colors = {
    "blue": "#4477AA",
    "cyan": "#66CCEE",
    "green": "#228833",
    "yellow": "#CCBB44",
    "grey": "#BBBBBB",  #  moved up to be used for ecological status of observed lakes
    "red": "#EE6677",
    "purple": "#AA3377",
}

# Set the default property-cycle and figure size for pyplots
color_cycler = cycler(color=list(colors.values()))  #  color cycler with 7 colors
linestyle_cycler = cycler(linestyle=["-", "--", "-.", ":", "-", "--", ":"])  #  7 styles
plt.rc("axes", prop_cycle=(color_cycler + linestyle_cycler))
plt.rc("figure", figsize=[10, 6.2])  #  golden ratio


# Function for accuracy score of predicted ecological status
def AccuracyScore(y_true, y_pred):
    """Convert continuous prediction of ecological status to categorical index and return accuracy score, i.e., the share of observed lakes each year where predicted ecological status matches the true ecological status (which LOO-CV omits from the dataset before applying imputation)."""
    eco_true, eco_pred = [], []  #  empy lists for storing transformed observations
    for a, b in zip([y_true, y_pred], [eco_true, eco_pred]):
        # Demarcation for categorical ecological status: Bad, Poor, Moderate, Good, High
        conditions = [
            a < 0.5,  # Bad
            (a >= 0.5) & (a < 1.5),  #  Poor
            (a >= 1.5) & (a < 2.5),  #  Moderate
            a >= 2.5,  #  Good or High
        ]
        b.append(np.select(conditions, [0, 1, 2, 3], default=np.nan))  #  add to list
    return accuracy_score(eco_true[0], eco_pred[0])


def stepwise_selection(subset, dummies, data, dfDummies, years):
    """Forward stepwise selection of predictors p to include in the model."""
    predictors = ["No dummies"] + dummies  #  list of possible predictors to include
    selected = []  #  empty list for storing selected predictors
    current_score, best_new_score = 0.0, 0.0  #  initial scores

    # DataFrames for storing accuracy scores by year and calculating weighted average
    scores = pd.DataFrame(subset.count(), index=years, columns=["n"]).astype(int)
    scores.loc["Total", "n"] = np.nan  #  row to calculate weighted average of scores
    scores_all = scores.copy()  #  scores for all sets of predictors being tested

    # DataFrames for storing ecological status by year and calculating weighted average
    status = scores.copy()  #  likewise, covers the years in the natural capital account
    status["Obs"] = (subset[years] < 2.5).sum() / status["n"]  #  eco status < good
    status.loc["Total", "Obs"] = (status["Obs"] * status["n"]).sum() / status["n"].sum()
    status_all = status.copy()  #  eco status for all sets of predictors being tested

    while current_score == best_new_score:
        names = []  #  empty list for storing model names
        scores_total = []  #  empty list for storing total score for each predictor
        sco = scores[["n"]].copy()  #  df for calculating weighted average of scores
        sta = status[["n"]].copy()  #  df for calculating weighted average of status

        for p in predictors:
            if p == "No dummies":  #  baseline model without any dummies
                df = data.copy()  #  df without predictors
                df.name = "No dummies"  #  name baseline model
            else:
                predictors_used = selected + [p]  #  selected predictors remain in model
                df = data.merge(dfDummies[predictors_used], on="wb")  #  with predictors
                df.name = ", ".join(predictors_used)  #  name model after its predictors
            names.append(df.name)  #  add model name to list of model names

            # Estimate share with less than good ecological status
            dfImp = pd.DataFrame(
                imputer.fit_transform(np.array(df)), index=df.index, columns=df.columns
            )

            # Subset to the waterbodies included in the subset and drop predictors
            dfImpSubset = dfImp.loc[subset.index, subset.columns]

            # Predicted share with less than good ecological status for relevant years
            sta[df.name] = (dfImpSubset[years] < 2.5).sum() / len(subset)

            # loop over each year t and waterbody i in (subset of) observed waterbodies
            for t in tqdm.tqdm(years):  #  time each model and report progress in years
                y = subset[subset[t].notnull()].index  #  index for LOO-CV at year t
                Y = pd.DataFrame(index=y)  #  empty df for observed and predicted values
                Y["true"] = df.loc[y, t]  #  column with the observed ('true') values
                Y["pred"] = pd.NA  #  empty column for storing predicted values
                for i in y:  #  loop over each observed value at year t
                    X = df.copy()  #  use a copy of the given DataFrame
                    X.loc[i, t] = pd.NA  #  set the observed value as missing
                    # Fit imputer and transform the dataset
                    X_imp = pd.DataFrame(
                        imputer.fit_transform(np.array(X)),
                        index=X.index,
                        columns=X.columns,
                    )
                    Y.loc[i, "pred"] = X_imp.loc[i, t]  #  store predicted value

                # Accuracy of predicted ecological status
                accuracy = AccuracyScore(Y["true"], Y["pred"])

                # Save accuracy score each year to DataFrame for scores
                sco.loc[t, df.name] = accuracy

            # Total accuracy weighted by number of observations used for LOO-CV each year
            for a, b in zip([scores_all, status_all], [sco, sta]):
                b.loc["Total", df.name] = (b[df.name] * b["n"]).sum() / b["n"].sum()
                a[df.name] = b[df.name]  #  scores & status by year for all predictors
            scores_total.append(sco.loc["Total", df.name])  #  score for each predictor

            print(df.name, "used for imputation. Accuracy score:", scores_total[-1])

            if p == "No dummies":
                break  #  save baseline model before stepwise selection of dummies

        best_new_score = max(scores_total)  #  best score

        if best_new_score > current_score:
            current_score = best_new_score  #  update current score
            i = scores_total.index(best_new_score)  #  index for predictor w. best score

            # Move dummy with the best new score from the list of predictors to selected
            selected.append(predictors.pop(i))

            # Save scores and status by year subject to the selected set of predictors
            for a, b in zip([scores, status], [sco, sta]):
                a[names[i]] = b[names[i]]  #  scores & status by year for best predictor

            if p == "No dummies":
                selected = []  #  after baseline model, start actual stepwise selection

        else:  #  if best_new_score == current_score (i.e., identical accuracy score)
            break  #  stop selection (including the predictor would increase variance)

        if predictors == []:  #  if all predictors have been included in the best model
            break  #  stop stepwise selection

    # Total number of observations that LOO-CV was performed over
    for s in (scores, status, scores_all, status_all):
        s.loc["Total", "n"] = s["n"].sum()

    # Save accuracy scores and share with less than good ecological status to CSV
    if subset is sparse:
        scores.to_csv("output/lakes_eco_imp_accuracy_sparse.csv")
        status.to_csv("output/lakes_eco_imp_LessThanGood_sparse.csv")
        scores_all.to_csv("output/lakes_eco_imp_accuracy_sparse_all.csv")
        status_all.to_csv("output/lakes_eco_imp_LessThanGood_sparse_all.csv")
    else:
        scores.to_csv("output/lakes_eco_imp_accuracy.csv")
        status.to_csv("output/lakes_eco_imp_LessThanGood.csv")
        scores_all.to_csv("output/lakes_eco_imp_accuracy_all.csv")
        status_all.to_csv("output/lakes_eco_imp_LessThanGood_all.csv")

    return selected, scores, status  #  selected predictors; scores and stats by year


########################################################################################
#   1. Data setup
########################################################################################
# Specify the working directory of the operating system
os.chdir(r"C:\Users\au687527\GitHub\GreenGDP\gis")

# Limit LOO-CV to loop over years used directly for the natural capital account
years = list(range(1989, 2020 + 1))

# Read DataFrames for observed ecological status and typology
dfEcoObs = pd.read_csv("output/lakes_eco_obs.csv", index_col="wb")
dfEcoObs.columns = dfEcoObs.columns.astype(int)
dfVP = pd.read_csv("output\\lakes_VP.csv", index_col="wb")

# Share of waterbodies by number of non-missing values
for n in range(0, len(dfEcoObs.columns) + 1):
    n, round(100 * sum(dfEcoObs.notna().sum(axis=1) == n) / len(dfEcoObs), 2)  # percent

# Subset of rows where only 1-4 values are non-missing
sparse = dfEcoObs[dfEcoObs.notna().sum(axis=1).isin([1, 2, 3, 4])]
sparse.count()  #  lowest number of non-missing values with support in all years
sparse.count().sum()  #  994 non-missing values in total to loop over with LOO-CV

# Merge DataFrames for ecological status (observed and basis analysis for VP3)
dfObs = dfEcoObs.merge(dfVP[["Basis"]], on="wb")

# Convert typology to integers
typ = dfVP[["ov_typ"]].copy()
typ.loc[:, "type"] = typ["ov_typ"].str.slice(6).astype(int)

# Create dummies for high Alkalinity, Brown, Saline, and Deep lakes
cond1 = [(typ["type"] >= 9) & (typ["type"] <= 16), typ["type"] == 17]
typ["Alkalinity"] = np.select(cond1, [1, np.nan], default=0)
cond2 = [typ["type"].isin([5, 6, 7, 8, 13, 14, 15, 16]), typ["type"] == 17]
typ["Brown"] = np.select(cond2, [1, np.nan], default=0)
cond3 = [typ["type"].isin([2, 3, 7, 8, 11, 12, 15, 16]), typ["type"] == 17]
typ["Saline"] = np.select(cond3, [1, np.nan], default=0)
cond4 = [typ["type"].isin(np.arange(2, 17, 2)), typ["type"] == 17]
typ["Deep"] = np.select(cond4, [1, np.nan], default=0)

# List dummies for typology
cols = ["Alkalinity", "Brown", "Saline", "Deep"]

# Merge DataFrames for typology and observed ecological status
dfTypology = dfObs.merge(typ[cols], on="wb")

# Create dummies for waterbody districts
distr = pd.get_dummies(dfVP["distr_id"]).astype(int)

# Extend dfTypology with dummy for district DK2 (Sealand, Lolland, Falster, and Møn)
dfDistrict = dfTypology.merge(distr["DK2"], on="wb")
cols.append("DK2")

# Set up DataFrames for descriptive statistics
dfSparse = dfDistrict.merge(sparse[[]], on="wb")  #  subset w. status observed 1-4 times
dfBasis = dfDistrict[dfDistrict["Basis"].notna()]
basis = dfEcoObs.merge(dfBasis[[]], on="wb")

# Overrepresentation of deep lakes
dfDistrict["Deep"].eq(1).sum()  #  151 deep lakes, of which only 6 are unobserved
dfDistrict[dfDistrict["Deep"] == 1][dfEcoObs.columns].dropna(how="all").shape[0]  #  145

# Empty dfs for storing distribution and mean ecological status by dummy respectively
VPstats = pd.DataFrame(columns=["Sparse subset", "Observed subset", "All in VP3"])
VPbasis = pd.DataFrame(
    columns=["Sparse subset", "Observed subset", "All in basis analysis"]  #  eco status
)

# Yearly distribution of observed lakes by typology and district
for a, b in zip([sparse, dfEcoObs], [dfSparse, dfDistrict]):
    # Subset b (dfDistrict or dfSparse) to lakes where status is observed at least once
    obs = b.loc[a.notna().any(axis=1)]  #  779 out of the 986 lakes in VP3

    # Subset b (dfDistrict or dfSparse) to lakes covered by basis analysis
    basis = b[b["Basis"].notna()]  #  791 out of 986 and 423 out of 423 respectively

    basisObs = basis.merge(obs, on="wb")  #  779 out of 779 obs lakes in dfDistrict

    # df for storing number of observed lakes and yearly distribution by dummies
    d = pd.DataFrame(index=a.columns)

    for c in cols:
        # Yearly distribution of observed lakes by dummy (typology and district)
        d[c] = b[b[c] == 1].count() / b.count()  #  share w. dummy each year
        d.loc["All obs", c] = len(obs[obs[c] == 1]) / len(obs)
        d.loc["All in VP3", c] = len(b[b[c] == 1]) / len(b)

        # Basis analysis share with less than good ecological status (< GES) by dummy
        VPbasis.loc[c, "Observed subset"] = (obs[obs[c] == 1]["Basis"] < 3).mean()
        VPbasis.loc[c, "All in basis analysis"] = (b[b[c] == 1]["Basis"] < 3).mean()

    # Share with < GES as assessed in the basis analysis for VP3 by dummy and subset
    VPbasis.loc["All", "Observed subset"] = (obs["Basis"] < 3).mean()  # observed subset
    VPbasis.loc["All", "All in basis analysis"] = (b["Basis"] < 3).mean()  # in basis a.

    # Number of lakes
    d["n"] = a.count().astype(int)  #  number of lakes observed each year
    d.loc["All obs", "n"] = len(obs)  #  number of lakes observed at least once
    d.loc["All in VP3", "n"] = len(a)  #  number of lakes included in VP3
    VPbasis.loc["n", "Observed subset"] = len(basisObs)  #  number in subset basis ∩ obs
    VPbasis.loc["n", "All in basis analysis"] = len(basis)  #  number of lakes in basis

    if a is sparse:
        VPstats["Sparse subset"] = d.loc["All obs", :].copy()  #  observed 1-3 times
        VPbasis["Sparse subset"] = VPbasis["Observed subset"]  #  observed 1-3 times
        d = d.drop("All obs")  #  sparse subset is already limited to observed lakes
        d = d.rename(index={"All in VP3": "All sparse"})  #  subset observed 1-3 times
        d.to_csv("output/lakes_VP_stats_yearly_sparse.csv")  #  yearly distributions
    else:
        VPstats["Observed subset"] = d.loc["All obs", :]  # observed at least onces
        VPstats["All in VP3"] = d.loc["All in VP3", :]  #  distribution of all in VP3
        d.to_csv("output/lakes_VP_stats_yearly.csv")  #  save yearly distributions
VPstats  #  overrepresentation of Brown and Saline lakes in sparse (share is ~50% above)
VPbasis  #  GES is overrepresented for Deep but underrepresented for DK2 and Brown

# Save descriptive statistics and mean basis analysis to CSV and LaTeX
for a, b in zip([VPstats, VPbasis], ["VP_stats", "VP_basis"]):
    a.to_csv("output/lakes_" + b + ".csv")  #  save means by subset to CSV
    f = {row: "{:0,.0f}".format if row == "n" else "{:0.2f}".format for row in a.index}
    with open("output/lakes_" + b + ".tex", "w") as tf:
        tf.write(a.apply(f, axis=1).to_latex(column_format="lccc"))  #  column alignment


########################################################################################
#   2. Subset selection (note: CV takes ~2 hours for sparse + ~11h for all observations)
########################################################################################
# # Example data for testing Forward Stepwise Selection with LOO-CV (takes ~5 seconds)
# dfEcoObs = pd.DataFrame(
#     {
#         1988: [0.5, 1.0, 1.5, 2.0, np.nan, 3.0],
#         1989: [0.6, 1.1, 1.6, np.nan, 2.6, 3.1],
#         1990: [0.7, 1.2, np.nan, 2.2, 2.7, 3.2],
#         1991: [0.8, np.nan, 1.8, 2.3, 2.8, 3.3],
#         1992: [np.nan, 1.4, 1.9, 2.4, 2.9, 3.4],
#         1993: [1.0, 1.5, 1.8, 2.4, 3.1, 3.5],
#     }
# )
# dfEcoObs.index.name = "wb"
# sparse = dfEcoObs[dfEcoObs.notna().sum(axis=1) == 5]
# dfObs = dfEcoObs.copy()
# dfTypology = dfObs.copy()
# dfTypology["Brown"] = [0, 0, 1, 1, 0, 0]  #  effect: 0.2 worse in 1993
# dfDistrict = dfTypology.copy()
# dfDistrict["DK1"] = [0, 0, 0, 1, 1, 0]  #  effect: 0.1 better in 1993
# cols = ["Brown", "DK1"]
# years = list(range(1989, 1993 + 1))

# Forward stepwise selection of dummies - CV over subset of sparsely observed lakes
kwargs = {"dummies": cols, "data": dfObs, "dfDummies": dfDistrict, "years": years}
selectedSparse, scoresSparse, statusSparse = stepwise_selection(subset=sparse, **kwargs)
scoresSparse
statusSparse

# Forward stepwise selection of dummies - CV over all observed values in all lakes
selected, scores, status = stepwise_selection(subset=dfEcoObs, **kwargs)
scores
status

########################################################################################
#   3. Visualization: Accuracy and share with less than good ecological status by year
########################################################################################
# Skip step 2 by reading DataFrames of accuracy score and ecological status from CSV
# scores = pd.read_csv("output/lakes_eco_imp_accuracy.csv", index_col=0)
# status = pd.read_csv("output/lakes_eco_imp_LessThanGood.csv", index_col=0)

# Accuracy score by year and selected predictors
scores.index = scores.index.astype(str)  #  convert index to string (to mimic read_csv)
sco = scores.drop(columns="n").drop(["1989", "Total"])  #  subset to relevant years
f1 = sco.plot(  #  bar plot accuracy scores
    kind="bar", ylabel="Accuracy in predicting observed ecological status"
).get_figure()
f1.savefig("output/lakes_eco_imp_accuracy.pdf", bbox_inches="tight")  #  save to PDF

# Share of lakes with less than good ecological status by year and selected predictors
status.index = status.index.astype(str)  #  convert index to string (to mimic read_csv)
status_years = status.drop(["1989", "Total"])  #  cover years in natural capital account
imp = status_years.drop(columns=["n", "Obs"])  #  imputed status by selected predictors
obs = status_years[["Obs"]]  #  ecological status of lakes observed the given year
obs.columns = ["Observed"]  #  rename 'Obs' to 'Observed'
sta = imp.merge(obs, left_index=True, right_index=True)  #  add Observed as last column
f2 = sta.plot(  #  plot share of lakes with less than good ecological status
    ylabel="Share of lakes with less than good ecological status"
).get_figure()
f2.savefig("output/lakes_eco_imp_LessThanGood.pdf", bbox_inches="tight")  #  save to PDF
