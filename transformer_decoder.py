# -*- coding: utf-8 -*-
"""Transformer GPT

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/1hhaX5U0HcGWvBt5Bawd80olOPPt8KKx8
"""

import os
import numpy as np
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
import pickle
import torch
import torch.nn as nn
import torch.optim as optim

from os import path

from torch.utils.data import DataLoader, TensorDataset

from sklearn.preprocessing import MinMaxScaler
from sklearn.preprocessing import StandardScaler
from sklearn.preprocessing import LabelEncoder

from sklearn.utils.class_weight import compute_class_weight

from sklearn import metrics
from sklearn import preprocessing
from sklearn.metrics import accuracy_score
from sklearn.model_selection import train_test_split, KFold
from sklearn.metrics import classification_report, accuracy_score, confusion_matrix, f1_score, precision_score, recall_score

from imblearn.under_sampling import RandomUnderSampler
from imblearn.over_sampling import RandomOverSampler


from collections import Counter

from google.colab import drive

drive.mount('/content/gdrive', force_remount=True)
os.chdir("/content/gdrive/MyDrive/Dataset")
data = pd.read_csv("/content/gdrive/MyDrive/Dataset/UNSW_NB15_training.csv")

"""# EDA"""

data.isnull().sum()
data['service'].replace('-', np.nan, inplace=True)

data.dropna(inplace=True)

"""# PRE-PROCESSING"""

features = pd.read_csv("/content/gdrive/MyDrive/Dataset/NUSW-NB15_features.csv")
features['Type '] = features['Type '].str.lower()
features.head()

nominal_names = features['Name'][features['Type ']=='nominal']
integer_names = features['Name'][features['Type ']=='integer']
binary_names = features['Name'][features['Type ']=='binary']
float_names = features['Name'][features['Type ']=='float']

cols = data.columns
nominal_names = cols.intersection(nominal_names)
integer_names = cols.intersection(integer_names)
binary_names = cols.intersection(binary_names)
float_names = cols.intersection(float_names)

# Converting integer columns to numeric
for c in integer_names:
  pd.to_numeric(data[c])

# Converting binary columns to numeric
for c in binary_names:
  pd.to_numeric(data[c])

# Converting float columns to numeric
for c in float_names:
  pd.to_numeric(data[c])

"""## One Hot Encoding"""

# Choose categorical data
num_col = data.select_dtypes(include='number').columns
cat_col = data.columns.difference(num_col)
cat_col = cat_col[1:]
data_cat = data[cat_col].copy()

# One hot encoding categorical column
data_cat = pd.get_dummies(data_cat,columns=cat_col)

# concat categorical data with main dataset
train = pd.concat([data, data_cat],axis=1)
train.drop(columns=cat_col,inplace=True)

"""## Normalization"""

# Choose numeric column except id and label
num_col = list(train.select_dtypes(include='number').columns)
num_col.remove('id')
num_col.remove('label')

# Using min max scaler to normalize data
minmax_scale = MinMaxScaler(feature_range=(0, 1))
def normalization(df,col):
  for i in col:
    arr = df[i]
    arr = np.array(arr)
    df[i] = minmax_scale.fit_transform(arr.reshape(len(arr),1))
  return df

data = normalization(train.copy(),num_col)

"""## Label Encoding"""

# One hot encoding on attack_cat column
multi_data = data.copy()
multi_label = pd.DataFrame(multi_data.attack_cat)
multi_data = pd.get_dummies(multi_data,columns=['attack_cat'])

le2 = preprocessing.LabelEncoder()
enc_label = multi_label.apply(le2.fit_transform)
multi_data['label'] = enc_label

"""## Correlation"""

num_col.append('label')

num_col = list(multi_data.select_dtypes(include='number').columns)
plt.figure(figsize=(20,8))
corr_multi = multi_data[num_col].corr()
sns.heatmap(corr_multi,vmax=1.0,annot=False)
plt.title('Correlation Matrix for Multi Labels',fontsize=16)

"""## Feature Selection"""

corr_ymulti = abs(corr_multi['label'])
highest_corr_multi = corr_ymulti[corr_ymulti >0.3]
highest_corr_multi.sort_values(ascending=True)
multi_cols = highest_corr_multi.index

multi_data = multi_data[multi_cols].copy()

"""# Data Splitting"""

X_multi = multi_data.drop(columns=['label'],axis=1)
y_multi = multi_data['label']
X_train_multi, X_test_multi, y_train_multi, y_test_multi = train_test_split(X_multi, y_multi, test_size=0.3, random_state=100)

"""# Transformer GPT"""

class GPTModel(nn.Module):
    def __init__(self, input_dim, num_classes):
        super(GPTModel, self).__init__()
        self.embedding = nn.Linear(input_dim, 64)
        self.transformer_decoder = nn.TransformerDecoder(
            nn.TransformerDecoderLayer(d_model=64, nhead=4, batch_first=True),
            num_layers=3)
        self.fc = nn.Linear(64, num_classes)

    def forward(self, x):
        x = self.embedding(x)
        x = x.unsqueeze(1)

        x_decoder = x

        x = self.transformer_decoder(x_decoder, x)
        x = x.mean(dim=1)
        x = self.fc(x)
        return x

"""## Without Class Balancing"""

scaler = StandardScaler()
X_multi = scaler.fit_transform(multi_data.drop(columns=['label'], axis=1).values)
y_multi = multi_data['label'].values

num_classes = len(np.unique(y_multi))

kf = KFold(n_splits=5, shuffle=True, random_state=50)
all_accuracy = []
conf_matrix_list = []
all_f1_scores = []

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

for fold, (train_index, val_index) in enumerate(kf.split(X_multi)):
    print(f'Fold {fold + 1}')

    X_train, X_val = X_multi[train_index], X_multi[val_index]
    y_train, y_val = y_multi[train_index], y_multi[val_index]

    X_train_tensor = torch.FloatTensor(X_train).to(device)
    y_train_tensor = torch.LongTensor(y_train).to(device)
    X_val_tensor = torch.FloatTensor(X_val).to(device)
    y_val_tensor = torch.LongTensor(y_val).to(device)

    train_dataset = TensorDataset(X_train_tensor, y_train_tensor)
    train_loader = DataLoader(train_dataset, batch_size=32, shuffle=True)

    model = GPTModel(input_dim=X_train.shape[1], num_classes=num_classes).to(device)

    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=0.001)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, 'max', patience=3, factor=0.5)

    best_accuracy = 0
    patience = 5
    trigger_times = 0

    num_epochs = 20
    for epoch in range(num_epochs):
        model.train()
        train_loss = 0.0
        for inputs, labels in train_loader:
            optimizer.zero_grad()
            outputs = model(inputs)
            loss = criterion(outputs, labels)
            loss.backward()
            optimizer.step()
            train_loss += loss.item()

        train_loss /= len(train_loader)

        model.eval()
        with torch.no_grad():
            y_pred_probs = model(X_val_tensor)
            _, y_pred = torch.max(y_pred_probs, 1)

        accuracy = accuracy_score(y_val, y_pred.cpu().numpy())

        if accuracy > best_accuracy:
            best_accuracy = accuracy
            torch.save(model.state_dict(), f'model_multi_fold_{fold + 1}.pt')
            trigger_times = 0
        else:
            trigger_times += 1

        if trigger_times >= patience:
            print(f'Early stopping triggered at epoch {epoch + 1}')
            break

        scheduler.step(accuracy)

        print(f'Epoch {epoch + 1}/{num_epochs}, Loss: {train_loss:.4f}, Accuracy: {accuracy * 100:.2f}%')

    conf_matrix = confusion_matrix(y_val, y_pred.cpu().numpy())
    all_accuracy.append(accuracy)
    conf_matrix_list.append(conf_matrix)

    f1 = f1_score(y_val, y_pred.cpu().numpy(), average='weighted', zero_division=0)
    precision = precision_score(y_val, y_pred.cpu().numpy(), average='weighted', zero_division=0)
    recall = recall_score(y_val, y_pred.cpu().numpy(), average='weighted', zero_division=0)
    all_f1_scores.append(f1)

    print(f'Accuracy for fold {fold + 1}: {accuracy * 100:.2f}%')
    print(f'F1 Score for fold {fold + 1}: {f1:.4f}')
    print(f'Precision for fold {fold + 1}: {precision:.4f}')
    print(f'Recall for fold {fold + 1}: {recall:.4f}')

    cls_report = classification_report(y_val, y_pred.cpu().numpy(), zero_division=0, target_names=le2.classes_)
    print(cls_report)

    # Plot confusion matrix for each fold
    plt.figure(figsize=(8, 6))
    sns.heatmap(conf_matrix, annot=True, fmt='.0f', cmap='Blues', cbar=False,
                xticklabels=[str(i) for i in range(num_classes)], yticklabels=[str(i) for i in range(num_classes)])
    plt.xlabel('Predicted Label')
    plt.ylabel('True Label')
    plt.title(f'Confusion Matrix for Fold {fold + 1}')
    plt.show()

# Average accuracy and F1 Score across folds
print(f'Average Accuracy: {np.mean(all_accuracy) * 100:.2f}%')
print(f'Average F1 Score: {np.mean(all_f1_scores):.4f}')

# Plotting the average confusion matrix
average_conf_matrix = np.mean(conf_matrix_list, axis=0)

plt.figure(figsize=(8, 6))
sns.heatmap(average_conf_matrix, annot=True, fmt='.0f', cmap='Blues', cbar=False,
            xticklabels=[str(i) for i in range(num_classes)], yticklabels=[str(i) for i in range(num_classes)])
plt.xlabel('Predicted Label')
plt.ylabel('True Label')
plt.title('Average Confusion Matrix Across Folds')
plt.show()

class_counts = multi_data['label'].value_counts()

plt.figure(figsize=(10, 6))
class_counts.plot(kind='bar')
plt.xlabel('Class')
plt.ylabel('Number of Instances')
plt.title('Class Distribution')
plt.xticks(rotation=0)
plt.show()

"""## With Class Balancing"""

scaler = StandardScaler()
X_multi = scaler.fit_transform(multi_data.drop(columns=['label'], axis=1).values)
y_multi = multi_data['label'].values

num_classes = len(np.unique(y_multi))

class_weights = compute_class_weight(class_weight='balanced', classes=np.unique(y_multi), y=y_multi)
class_weights = torch.FloatTensor(class_weights)

kf = KFold(n_splits=5, shuffle=True, random_state=50)
all_accuracy = []
conf_matrix_list = []
all_f1_scores = []

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
class_weights = class_weights.to(device)

for fold, (train_index, val_index) in enumerate(kf.split(X_multi)):
    print(f'Fold {fold + 1}')

    X_train, X_val = X_multi[train_index], X_multi[val_index]
    y_train, y_val = y_multi[train_index], y_multi[val_index]

    X_train_tensor = torch.FloatTensor(X_train).to(device)
    y_train_tensor = torch.LongTensor(y_train).to(device)
    X_val_tensor = torch.FloatTensor(X_val).to(device)
    y_val_tensor = torch.LongTensor(y_val).to(device)

    train_dataset = TensorDataset(X_train_tensor, y_train_tensor)
    train_loader = DataLoader(train_dataset, batch_size=32, shuffle=True)

    model = GPTModel(input_dim=X_train.shape[1], num_classes=num_classes).to(device)

    criterion = nn.CrossEntropyLoss(weight=class_weights)
    optimizer = torch.optim.Adam(model.parameters(), lr=0.001)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, 'max', patience=3, factor=0.5)

    best_accuracy = 0
    patience = 5
    trigger_times = 0

    num_epochs = 20
    for epoch in range(num_epochs):
        model.train()
        train_loss = 0.0
        for inputs, labels in train_loader:
            optimizer.zero_grad()
            outputs = model(inputs)
            loss = criterion(outputs, labels)
            loss.backward()
            optimizer.step()
            train_loss += loss.item()

        train_loss /= len(train_loader)

        model.eval()
        with torch.no_grad():
            y_pred_probs = model(X_val_tensor)
            _, y_pred = torch.max(y_pred_probs, 1)

        accuracy = accuracy_score(y_val, y_pred.cpu().numpy())

        if accuracy > best_accuracy:
            best_accuracy = accuracy
            torch.save(model.state_dict(), f'model_multi_fold_{fold + 1}.pt')
            trigger_times = 0
        else:
            trigger_times += 1

        if trigger_times >= patience:
            print(f'Early stopping triggered at epoch {epoch + 1}')
            break

        scheduler.step(accuracy)

        print(f'Epoch {epoch + 1}/{num_epochs}, Loss: {train_loss:.4f}, Accuracy: {accuracy * 100:.2f}%')

    conf_matrix = confusion_matrix(y_val, y_pred.cpu().numpy())
    all_accuracy.append(accuracy)
    conf_matrix_list.append(conf_matrix)

    f1 = f1_score(y_val, y_pred.cpu().numpy(), average='weighted', zero_division=0)
    precision = precision_score(y_val, y_pred.cpu().numpy(), average='weighted', zero_division=0)
    recall = recall_score(y_val, y_pred.cpu().numpy(), average='weighted', zero_division=0)
    all_f1_scores.append(f1)

    print(f'Accuracy for fold {fold + 1}: {accuracy * 100:.2f}%')
    print(f'F1 Score for fold {fold + 1}: {f1:.4f}')
    print(f'Precision for fold {fold + 1}: {precision:.4f}')
    print(f'Recall for fold {fold + 1}: {recall:.4f}')

    cls_report = classification_report(y_val, y_pred.cpu().numpy(), zero_division=0, target_names=le2.classes_)
    print(cls_report)

    # Plot confusion matrix for each fold
    plt.figure(figsize=(8, 6))
    sns.heatmap(conf_matrix, annot=True, fmt='.0f', cmap='Blues', cbar=False,
                xticklabels=[str(i) for i in range(num_classes)], yticklabels=[str(i) for i in range(num_classes)])
    plt.xlabel('Predicted Label')
    plt.ylabel('True Label')
    plt.title(f'Confusion Matrix for Fold {fold + 1}')
    plt.show()

# Average accuracy and F1 Score across folds
print(f'Average Accuracy: {np.mean(all_accuracy) * 100:.2f}%')
print(f'Average F1 Score: {np.mean(all_f1_scores):.4f}')

# Plotting the average confusion matrix
average_conf_matrix = np.mean(conf_matrix_list, axis=0)

plt.figure(figsize=(8, 6))
sns.heatmap(average_conf_matrix, annot=True, fmt='.0f', cmap='Blues', cbar=False,
            xticklabels=[str(i) for i in range(num_classes)], yticklabels=[str(i) for i in range(num_classes)])
plt.xlabel('Predicted Label')
plt.ylabel('True Label')
plt.title('Average Confusion Matrix Across Folds')
plt.show()

"""#Class Balancing

## Random Over Sampling
"""

scaler = StandardScaler()
X_multi = scaler.fit_transform(multi_data.drop(columns=['label'], axis=1).values)
y_multi = multi_data['label'].values

num_classes = len(np.unique(y_multi))

kf = KFold(n_splits=5, shuffle=True, random_state=50)
all_accuracy = []
conf_matrix_list = []
all_f1_scores = []

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

for fold, (train_index, val_index) in enumerate(kf.split(X_multi)):
    print(f'Fold {fold + 1}')

    X_train, X_val = X_multi[train_index], X_multi[val_index]
    y_train, y_val = y_multi[train_index], y_multi[val_index]

    ros = RandomOverSampler(random_state=42)
    X_train, y_train = ros.fit_resample(X_train, y_train)

    X_train_tensor = torch.FloatTensor(X_train).to(device)
    y_train_tensor = torch.LongTensor(y_train).to(device)
    X_val_tensor = torch.FloatTensor(X_val).to(device)
    y_val_tensor = torch.LongTensor(y_val).to(device)

    train_dataset = TensorDataset(X_train_tensor, y_train_tensor)
    train_loader = DataLoader(train_dataset, batch_size=32, shuffle=True)

    model = GPTModel(input_dim=X_train.shape[1], num_classes=num_classes).to(device)

    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=0.001)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, 'max', patience=3, factor=0.5)

    best_accuracy = 0
    patience = 5
    trigger_times = 0

    num_epochs = 20
    for epoch in range(num_epochs):
        model.train()
        train_loss = 0.0
        for inputs, labels in train_loader:
            optimizer.zero_grad()
            outputs = model(inputs)
            loss = criterion(outputs, labels)
            loss.backward()
            optimizer.step()
            train_loss += loss.item()

        train_loss /= len(train_loader)

        model.eval()
        with torch.no_grad():
            y_pred_probs = model(X_val_tensor)
            _, y_pred = torch.max(y_pred_probs, 1)

        accuracy = accuracy_score(y_val, y_pred.cpu().numpy())

        if accuracy > best_accuracy:
            best_accuracy = accuracy
            torch.save(model.state_dict(), f'model_multi_fold_{fold + 1}.pt')
            trigger_times = 0
        else:
            trigger_times += 1

        if trigger_times >= patience:
            print(f'Early stopping triggered at epoch {epoch + 1}')
            break

        scheduler.step(accuracy)

        print(f'Epoch {epoch + 1}/{num_epochs}, Loss: {train_loss:.4f}, Accuracy: {accuracy * 100:.2f}%')

    conf_matrix = confusion_matrix(y_val, y_pred.cpu().numpy())
    all_accuracy.append(accuracy)
    conf_matrix_list.append(conf_matrix)

    f1 = f1_score(y_val, y_pred.cpu().numpy(), average='weighted', zero_division=0)
    precision = precision_score(y_val, y_pred.cpu().numpy(), average='weighted', zero_division=0)
    recall = recall_score(y_val, y_pred.cpu().numpy(), average='weighted', zero_division=0)
    all_f1_scores.append(f1)

    print(f'Accuracy for fold {fold + 1}: {accuracy * 100:.2f}%')
    print(f'F1 Score for fold {fold + 1}: {f1:.4f}')
    print(f'Precision for fold {fold + 1}: {precision:.4f}')
    print(f'Recall for fold {fold + 1}: {recall:.4f}')

    cls_report = classification_report(y_val, y_pred.cpu().numpy(), zero_division=0, target_names=le2.classes_)
    print(cls_report)

    # Plot confusion matrix for each fold
    plt.figure(figsize=(8, 6))
    sns.heatmap(conf_matrix, annot=True, fmt='.0f', cmap='Blues', cbar=False,
                xticklabels=[str(i) for i in range(num_classes)], yticklabels=[str(i) for i in range(num_classes)])
    plt.xlabel('Predicted Label')
    plt.ylabel('True Label')
    plt.title(f'Confusion Matrix for Fold {fold + 1}')
    plt.show()

# Average accuracy and F1 Score across folds
print(f'Average Accuracy: {np.mean(all_accuracy) * 100:.2f}%')
print(f'Average F1 Score: {np.mean(all_f1_scores):.4f}')

# Plotting the average confusion matrix
average_conf_matrix = np.mean(conf_matrix_list, axis=0)

plt.figure(figsize=(8, 6))
sns.heatmap(average_conf_matrix, annot=True, fmt='.0f', cmap='Blues', cbar=False,
            xticklabels=[str(i) for i in range(num_classes)], yticklabels=[str(i) for i in range(num_classes)])
plt.xlabel('Predicted Label')
plt.ylabel('True Label')
plt.title('Average Confusion Matrix Across Folds')
plt.show()

class_counts = multi_data['label'].value_counts()

plt.figure(figsize=(10, 6))
class_counts.plot(kind='bar')
plt.xlabel('Class')
plt.ylabel('Number of Instances')
plt.title('Class Distribution')
plt.xticks(rotation=0)
plt.show()

"""## Random Under Sampling"""

scaler = StandardScaler()
X_multi = scaler.fit_transform(multi_data.drop(columns=['label'], axis=1).values)
y_multi = multi_data['label'].values

num_classes = len(np.unique(y_multi))

kf = KFold(n_splits=5, shuffle=True, random_state=50)
all_accuracy = []
conf_matrix_list = []
all_f1_scores = []

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

for fold, (train_index, val_index) in enumerate(kf.split(X_multi)):
    print(f'Fold {fold + 1}')

    X_train, X_val = X_multi[train_index], X_multi[val_index]
    y_train, y_val = y_multi[train_index], y_multi[val_index]

    ros = RandomUnderSampler(random_state=42)
    X_train, y_train = ros.fit_resample(X_train, y_train)

    X_train_tensor = torch.FloatTensor(X_train).to(device)
    y_train_tensor = torch.LongTensor(y_train).to(device)
    X_val_tensor = torch.FloatTensor(X_val).to(device)
    y_val_tensor = torch.LongTensor(y_val).to(device)

    train_dataset = TensorDataset(X_train_tensor, y_train_tensor)
    train_loader = DataLoader(train_dataset, batch_size=32, shuffle=True)

    model = GPTModel(input_dim=X_train.shape[1], num_classes=num_classes).to(device)

    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=0.001)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, 'max', patience=3, factor=0.5)

    best_accuracy = 0
    patience = 5
    trigger_times = 0

    num_epochs = 20
    for epoch in range(num_epochs):
        model.train()
        train_loss = 0.0
        for inputs, labels in train_loader:
            optimizer.zero_grad()
            outputs = model(inputs)
            loss = criterion(outputs, labels)
            loss.backward()
            optimizer.step()
            train_loss += loss.item()

        train_loss /= len(train_loader)

        model.eval()
        with torch.no_grad():
            y_pred_probs = model(X_val_tensor)
            _, y_pred = torch.max(y_pred_probs, 1)

        accuracy = accuracy_score(y_val, y_pred.cpu().numpy())

        if accuracy > best_accuracy:
            best_accuracy = accuracy
            torch.save(model.state_dict(), f'model_multi_fold_{fold + 1}.pt')
            trigger_times = 0
        else:
            trigger_times += 1

        if trigger_times >= patience:
            print(f'Early stopping triggered at epoch {epoch + 1}')
            break

        scheduler.step(accuracy)

        print(f'Epoch {epoch + 1}/{num_epochs}, Loss: {train_loss:.4f}, Accuracy: {accuracy * 100:.2f}%')

    conf_matrix = confusion_matrix(y_val, y_pred.cpu().numpy())
    all_accuracy.append(accuracy)
    conf_matrix_list.append(conf_matrix)

    f1 = f1_score(y_val, y_pred.cpu().numpy(), average='weighted', zero_division=0)
    precision = precision_score(y_val, y_pred.cpu().numpy(), average='weighted', zero_division=0)
    recall = recall_score(y_val, y_pred.cpu().numpy(), average='weighted', zero_division=0)
    all_f1_scores.append(f1)

    print(f'Accuracy for fold {fold + 1}: {accuracy * 100:.2f}%')
    print(f'F1 Score for fold {fold + 1}: {f1:.4f}')
    print(f'Precision for fold {fold + 1}: {precision:.4f}')
    print(f'Recall for fold {fold + 1}: {recall:.4f}')

    cls_report = classification_report(y_val, y_pred.cpu().numpy(), zero_division=0, target_names=le2.classes_)
    print(cls_report)

    # Plot confusion matrix for each fold
    plt.figure(figsize=(8, 6))
    sns.heatmap(conf_matrix, annot=True, fmt='.0f', cmap='Blues', cbar=False,
                xticklabels=[str(i) for i in range(num_classes)], yticklabels=[str(i) for i in range(num_classes)])
    plt.xlabel('Predicted Label')
    plt.ylabel('True Label')
    plt.title(f'Confusion Matrix for Fold {fold + 1}')
    plt.show()

# Average accuracy and F1 Score across folds
print(f'Average Accuracy: {np.mean(all_accuracy) * 100:.2f}%')
print(f'Average F1 Score: {np.mean(all_f1_scores):.4f}')

# Plotting the average confusion matrix
average_conf_matrix = np.mean(conf_matrix_list, axis=0)

plt.figure(figsize=(8, 6))
sns.heatmap(average_conf_matrix, annot=True, fmt='.0f', cmap='Blues', cbar=False,
            xticklabels=[str(i) for i in range(num_classes)], yticklabels=[str(i) for i in range(num_classes)])
plt.xlabel('Predicted Label')
plt.ylabel('True Label')
plt.title('Average Confusion Matrix Across Folds')
plt.show()

class_counts = multi_data['label'].value_counts()

plt.figure(figsize=(10, 6))
class_counts.plot(kind='bar')
plt.xlabel('Class')
plt.ylabel('Number of Instances')
plt.title('Class Distribution')
plt.xticks(rotation=0)
plt.show()