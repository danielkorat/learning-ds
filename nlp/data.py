import operator
from os.path import dirname, realpath, isfile
import pickle
from pathlib import Path
from collections import defaultdict
from abc import abstractmethod

import torch
from torch.utils.data import DataLoader, random_split
import pytorch_lightning as pl
from datasets import load_dataset
from numpy import log
from torchtext.vocab import CharNGram
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt
import json
from tqdm import tqdm

import numpy as np
from nltk.lm import NgramCounter
from nltk.util import ngrams

CACHE_DIR = Path(dirname(realpath(__file__))) / "data"
VECTORS_DIR = CACHE_DIR / ".vector_cache"

VECTORS = CharNGram


class HuggingfaceDataModule(pl.LightningDataModule):
    def __init__(self, config):
        super().__init__()
        self.batch_size = config["batch_size"]
        self.num_workers = 88  # config['num_workers']

    def prepare_data(self):
        # download only
        self.download_and_preprocess()

    @staticmethod
    @abstractmethod
    def download_and_preprocess():
        raise NotImplementedError()

    def setup(self, stage):
        ds = self.download_and_preprocess()
        self.ds = [i[2] for i in ds]
        ds = [i[:2] for i in ds]
        # Splits
        split_sizes = [int(len(ds) * 0.7), int(len(ds) * 0.15), int(len(ds) * 0.15)]
        if sum(split_sizes) < len(ds):
            split_sizes[0] += len(ds) - sum(split_sizes)

        self.train_dataset, self.val_dataset, self.test_dataset = random_split(ds, split_sizes)

    def split_dataloader(self, split):
        return DataLoader(
            split, batch_size=self.batch_size, num_workers=self.num_workers
        )

    def train_dataloader(self):
        return self.split_dataloader(self.train_dataset)

    def val_dataloader(self):
        return self.split_dataloader(self.val_dataset)

    def test_dataloader(self):
        return self.split_dataloader(self.test_dataset)


class WordCountDataModule(HuggingfaceDataModule):
    ds_name = "conll2003"
    ds_cache = CACHE_DIR / "word_count.pickle"

    def __init__(self, config):
        super().__init__(config)

    @staticmethod
    def download_and_preprocess():
        if isfile(WordCountDataModule.ds_cache) and False:
            with open(WordCountDataModule.ds_cache, "rb") as ds_pickle:
                word_count_ds = pickle.load(ds_pickle)

        else:
            conll_dataset = load_dataset(
                path=WordCountDataModule.ds_name, cache_dir=CACHE_DIR
            )
            embedder = VECTORS(cache=VECTORS_DIR)

            counts = defaultdict(int)
            for split in "train", "test", "validation":
                for example in conll_dataset[split]:
                    for token in example["tokens"]:
                        counts[token.lower()] += 1
            word_count_ds = []
            for t, c in counts.items():
                word_count_ds.append(
                    (embedder[t].float(), torch.tensor([log(c)], dtype=torch.float), t)
                )

            with open(WordCountDataModule.ds_cache, "wb") as ds_pickle:
                pickle.dump(word_count_ds, ds_pickle)
        return word_count_ds


class WikiDataModule(HuggingfaceDataModule):
    ds_name = "wikicorpus"
    ds_cache = CACHE_DIR / "wiki.pickle"

    def __init__(self, config):
        super().__init__(config)

    @staticmethod
    def download_and_preprocess():
        conll_dataset = load_dataset(
            path=WikiDataModule.ds_name, name="tagged_en", cache_dir=CACHE_DIR
        )


def plot_token_frequencies(ds_name, limit_prop, tokens_key='tokens', **kwargs):
    counts = defaultdict(int)
    ds = load_dataset(ds_name, cache_dir=CACHE_DIR, **kwargs)
    stop_counter = 0
    examples = ds['train']
    limit = int(limit_prop * len(examples))
    print(f'Num of examples used: {limit}')

    for example in tqdm(examples, total=limit):
        if stop_counter == limit:
            break
        stop_counter += 1

        for token in example[tokens_key]:
            counts[token.lower()] += 1

    for w, count in counts.items():
        counts[w] = log(count)

    plot_frequencies(counts, xlabel="sorted items in log scale",
                    y_label="frequency in log scale", legend=f"{ds_name} ({int(limit_prop * 100)}%)",
                    save_name='log_frequency_{ds_name}_{limit_prop}')

def plot_frequencies(counts: dict, xlabel, ylabel, legend, save_name):
    sorted_counts = sorted(counts.values(), reverse=True)

    print(f'Num of unique tokens: {len(counts)}')
    df = pd.DataFrame(data=sorted_counts)
    df.index = log(df.index + 1)

    fig = df.plot().get_figure()
    plt.xlabel(xlabel)
    plt.ylabel(ylabel)
    plt.legend([legend])
    fig.savefig(f'nlp/{save_name}.png')


def get_ngram_counts(ds_name, limit_prop, n=2, tokens_key='tokens', **kwargs):
    ds = load_dataset(ds_name, cache_dir=CACHE_DIR, **kwargs)['train']
    limit = int(limit_prop * len(ds))

    print('Computing n-grams...')
    n_grams = []
    for i, s in tqdm(enumerate(ds), total=limit):
        if i == limit:
            break
        n_grams.append(ngrams(s[tokens_key], n))

    del ds

    print('Counting n-grams...')
    res = {}
    for a, b_list in tqdm(NgramCounter(n_grams)[n].items()):
        for b, cnt in b_list.items():
            res[(a[0], b)] = cnt

    del n_grams
    # sorted_res = sorted(res.items(), key=operator.itemgetter(1), reverse=True)

    xs, ys = [], []
    for (a, b), count in res.items():
        xs.append(' '.join((str(a), str(b))))
        ys.append(count)

    print(f'Number of examples used: {limit}')
    print(f'Number of bigrams: {len(res)}')

    del res

    # with open(f'nlp/{n}_gram_counts_{ds_name}_{limit_prop * 100}%.json', 'w') as f:
    #     json.dump(sorted_res, f, indent=2)

    np.savez_compressed(f'nlp/{n}_gram_counts_{ds_name}_{limit_prop * 100}%.npz',
            x=np.array(xs), y=np.array(ys))

if __name__== "__main__":
    # plot_frequencies('wikicorpus', limit_prop=0.1, tokens_key='sentence', name='tagged_en')

    wiki_bigrams = get_ngram_counts('wikicorpus', limit_prop=0.05, n=2, tokens_key='sentence', name='tagged_en')
