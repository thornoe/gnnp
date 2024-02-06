"""
Name:       streams_CV.py

Label:      Impute missing values in longitudinal data on ecological status of streams.

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

import numpy as np
import pandas as pd
import tqdm
from matplotlib import pyplot as plt
from sklearn.experimental import enable_iterative_imputer  # noqa
from sklearn.impute import IterativeImputer
from sklearn.metrics import accuracy_score

# Color-blind-friendly ordinal scale, modified from: gist.github.com/thriveth/8560036
ColorCycle = {
    "blue": "#377eb8",
    "orange": "#ff7f00",
    "green": "#4daf4a",
    "pink": "#f781bf",
    "gray": "#999999",  #  moved up (but still below pink)
    "brown": "#a65628",
    "purple": "#984ea3",
    "yellow": "#dede00",
    "red": "#e41a1c",  #  moved down
}

# Set the default color map and figure size for pyplots
plt.rcParams["axes.prop_cycle"] = plt.cycler("color", list(ColorCycle.values()))
plt.rcParams["figure.figsize"] = [12, 6]  #  wide format (appendix with wide margins)


# Function for score
def AccuracyScore(y_true, y_pred):
    """Convert DVFI fauna index for streams to categorical index of ecological status and return accuracy score, i.e., the share of observed streams each year where predicted ecological status matches the true ecological status (which LOO-CV omits from the dataset before applying imputation)."""
    eco_true, eco_pred = [], []  #  empy lists for storing transformed observations
    for a, b in zip([y_true, y_pred], [eco_true, eco_pred]):
        # Categorical variable for ecological status: Bad, Poor, Moderate, Good, High
        conditions = [
            a < 1.5,  # Bad
            (a >= 1.5) & (a < 3.5),  #  Poor
            (a >= 3.5) & (a < 4.5),  #  Moderate
            a >= 4.5,  #  Good or High
        ]
        b.append(np.select(conditions, [0, 1, 2, 3], default=np.nan))  #  add to list
    return accuracy_score(eco_true[0], eco_pred[0])


########################################################################################
#   1. Data setup
########################################################################################
# Specify the working directory of the operating system
os.chdir(r"C:\Users\au687527\GitHub\GreenGDP\gis")

# Limit LOO-CV to loop over years used directly for the natural capital account
years = list(range(1989, 2020 + 1))

# Read DataFrames for observed biophysical indicator and typology
dfIndObs = pd.read_csv("output/streams_ind_obs.csv", index_col="wb")
dfIndObs.columns = dfIndObs.columns.astype(int)
dfVP = pd.read_csv("output\\streams_VP.csv", index_col="wb")

# Include ecological status as assessed in basis analysis for VP3
basis = dfVP[["til_oko_bb"]].copy()  #  bottom fauna measured as DVFI index

# Define a dictionary to map the Danish strings to an ordinal scale
status_dict = {
    "Dårlig økologisk tilstand": 0,
    "Ringe økologisk tilstand": 1,
    "Moderat økologisk tilstand": 2,
    "God økologisk tilstand": 3,
    "Høj økologisk tilstand": 4,
    "Dårligt økologisk potentiale": 0,
    "Ringe økologisk potentiale": 1,
    "Moderat økologisk potentiale": 2,
    "Godt økologisk potentiale": 3,
    "Maksimalt økologisk potentiale": 4,
    "Ukendt": np.nan,
}

# Replace the Danish strings in the DataFrame with the corresponding ordinal values
basis.replace(status_dict, inplace=True)
basis.columns = ["basis"]
basis["basis"].unique()

# Merge DataFrames for typology and observed biophysical indicator
dfObs = dfIndObs.merge(basis, on="wb")

# Create dummies for typology
typ = pd.get_dummies(dfVP["ov_typ"]).astype(int)
typ["softBottom"] = typ["RW4"] + typ["RW5"]
typ.columns = [
    "small",
    "medium",
    "large",
    "smallSoftBottom",
    "mediumSoftBottom",
    "softBottom",
]

# List dummies for typology
cols = ["small", "medium", "large", "softBottom"]

# Merge DataFrames for typology and observed biophysical indicator
dfTypology = dfObs.merge(typ[cols], on="wb")

# Create dummies for natural, artificial, and heavily modified water bodies
natural = pd.get_dummies(dfVP["na_kun_stm"]).astype(int)
natural.columns = ["artificial", "natural", "heavily modified"]

# Merge DataFrames for typology and natural water bodies
dfNatural = dfTypology.merge(natural["natural"], on="wb")
cols.append("natural")  #  add to list of dummies

# Create dummies for water body district
distr = pd.get_dummies(dfVP["distr_id"]).astype(int)

# Extend dfNatural with dummy for district DK2 (Sealand, Lolland, Falster, and Møn)
dfDistrict = dfNatural.merge(distr["DK2"], on="wb")
cols.append("DK2")  #  add to list of dummies

# DataFrame for storing number of observed streams and yearly distribution by dummies
d = pd.DataFrame(dfIndObs.count(), index=dfIndObs.columns, columns=["n"]).astype(int)

# Yearly distribution of observed streams by typology and district
for c in cols:
    d[c] = 100 * dfDistrict[dfDistrict[c] == 1].count() / dfDistrict.count()
    d.loc["All VP3", c] = 100 * len(dfDistrict[dfDistrict[c] == 1]) / len(dfDistrict)
d.loc["All VP3", "n"] = len(dfDistrict)
d.to_csv("output/streams_VP_stats.csv")
d.loc["All VP3", :]

########################################################################################
#   2. Multivariate feature imputation (note: LOO-CV takes ≤ 24 hours for each model)
########################################################################################
# Iterative imputer using the default BayesianRidge() estimator with increased tolerance
imputer = IterativeImputer(tol=1e-1, random_state=0)

# Example data for testing LOO-CV below (takes ~3 seconds rather than ~3 days to run)
# dfIndObs = pd.DataFrame(
#     {
#         1988: [2.5, 3.0, 3.5, 4.0, np.nan],
#         1989: [2.6, 3.1, 3.6, np.nan, 4.6],
#         1990: [2.7, 3.2, np.nan, 4.2, 4.7],
#         1991: [2.8, np.nan, 3.8, 4.3, 4.8],
#         1992: [np.nan, 3.4, 3.9, 4.4, 4.9],
#     }
# )
# dfObs = dfIndObs.copy()
# dfTypology = dfObs.copy()
# dfTypology["small"] = [1, 1, 0, 0, 0]
# dfNatural = dfTypology.copy()
# dfNatural["natural"] = [0, 1, 1, 0, 0]
# dfDistrict = dfNatural.copy()
# dfDistrict["DK2"] = [1, 0, 1, 0, 0]
# years = list(range(1989, 1992 + 1))

# DataFrame for storing accuracy scores by year and calculating weighted average
scores = pd.DataFrame(dfIndObs.count(), index=years, columns=["n"]).astype(int)

# DataFrame for storing ecological status by year and calculating weighted average
status = pd.DataFrame(dfIndObs.count(), index=dfIndObs.columns, columns=["n"])

# Mean ecological status by year for the n observations that don'nt have missing values
status["Obs"] = (dfIndObs < 4.5).sum() / status["n"]  #  ecological status < good
status.loc["Total", "Obs"] = (status["Obs"] * status["n"]).sum() / status["n"].sum()

# Leave-one-out cross-validation (LOO-CV) loop over every observed stream and year
dfObs.name = "No dummies"  #  name model without any dummies
dfTypology.name = "Typology"  #  name model with dummies for typology
dfNatural.name = "Typ & natural"  #  name model with dummies for typology and natural
dfDistrict.name = "Typ, nat, & DK2"  #  name model with dummies for typ, nat, & district
for df in (dfObs, dfTypology, dfNatural, dfDistrict):  #  LOO-CV w. different dummies
    # Impute missing values based on all observations (without cross-validation)
    df_imp = pd.DataFrame(
        imputer.fit_transform(np.array(df)), index=df.index, columns=df.columns
    )
    # From imputed data, store estimated share with less than good ecological status
    status[df.name] = (df_imp[dfIndObs.columns] < 4.5).sum() / len(df)

    # For each year t, apply leave-one-out cross-validation
    print(df.name, "used for imputation. LOO-CV of observed streams each year:")
    for t in tqdm.tqdm(years):  #  time each model and report its progress in years
        y = df[df[t].notnull()].index  #  index for observed values at year t
        Y = pd.DataFrame(index=y)  #  empty df for observed and predicted values
        Y["true"] = df.loc[y, t]  #  column with the observed ('true') values
        Y["pred"] = pd.NA  #  empty column for storing predicted values
        for i in y:  #  loop over each observed value at year t
            X = df.copy()  #  use a copy of the given DataFrame
            X.loc[i, t] = pd.NA  #  set the observed value as missing
            # Fit imputer and transform the dataset
            X_imp = pd.DataFrame(
                imputer.fit_transform(np.array(X)), index=X.index, columns=X.columns
            )
            Y.loc[i, "pred"] = X_imp.loc[i, t]  #  store predicted value

        # Accuracy of ecological status after converting DVFI fauna index for streams
        accuracy = AccuracyScore(Y["true"], Y["pred"])

        # Save accuracy score each year to DataFrame for scores
        scores.loc[t, df.name] = accuracy

    # Totals weighted by number of observations
    for s in (scores, status):
        s.loc["Total", df.name] = (s[df.name] * s["n"]).sum() / s["n"].sum()

    # Save accuracy scores and share with less than good ecological status to CSV
    scores.to_csv("output/streams_eco_imp_accuracy_" + df.name + ".csv")
    status.to_csv("output/streams_eco_imp_LessThanGood_" + df.name + ".csv")

# Change in accuracy or predicted status due to dummy (difference from "No dummies")
scores.loc["Change", :] = scores.loc["Total", :] - scores.loc["Total", "No dummies"]
scores.loc["Change", :] * 100  #  report in percentage points

# Total number of observations that LOO-CV was performed over
for s in (scores, status):
    s.loc["Total", "n"] = s["n"].sum()

# Save accuracy scores and share with less than good ecological status to CSV
scores.to_csv("output/streams_eco_imp_accuracy.csv")
status.to_csv("output/streams_eco_imp_LessThanGood.csv")

########################################################################################
#   3. Visualization: Accuracy and share with less than good ecological status by year
########################################################################################
# Read accuracy scores and share with less than good ecological status from CSV
# scores = pd.read_csv("output/streams_eco_imp_accuracy.csv", index_col=0)
sco = scores.drop(columns="n").drop(["Total", "Change"])
# status = pd.read_csv("output/streams_eco_imp_LessThanGood.csv", index_col=0)
# Reorder and rename 'Obs' to 'Observed'
sta = status[
    ["No dummies", "Typology", "Typ & natural", "Typ, nat, & DK2", "Obs"]
].drop("Total")
sta.columns = ["No dummies", "Typology", "Typ & natural", "Typ, nat, & DK2", "Observed"]

# Bar plot accuracy scores
f1 = sco.plot(
    kind="bar", ylabel="Accuracy in predicting observed ecological status"
).get_figure()
f1.savefig("output/streams_eco_imp_accuracy.pdf", bbox_inches="tight")

# Plot share of streams with less than good ecological status
f2 = sta.plot(
    ylabel="Share of streams with less than good ecological status"
).get_figure()
f2.savefig("output/streams_eco_imp_LessThanGood.pdf", bbox_inches="tight")
