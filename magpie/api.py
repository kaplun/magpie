from __future__ import division, unicode_literals, print_function

import os
import time

import numpy as np
import sys

from magpie.base.build_matrices import build_train_matrices, build_test_matrices
from magpie.base.document import Document
from magpie.base.global_index import build_global_frequency_index
from magpie.base.model import LearningModel
from magpie.base.word2vec import get_word2vec_model
from magpie.config import MODEL_PATH, HEP_TRAIN_PATH, HEP_ONTOLOGY, \
    HEP_TEST_PATH, BATCH_SIZE, NB_EPOCHS, WORD2VEC_MODELPATH
from magpie.evaluation.standard_evaluation import evaluate_results
from magpie.misc.utils import save_to_disk, load_from_disk
from magpie.nn.models import get_nn_model
from magpie.nn.nn import extract as nn_extract
from magpie.utils import get_ontology, get_documents


def extract_from_file(path_to_file, model_path, **kwargs):
    """ Extract keywords from a file """
    doc = Document(0, path_to_file)
    return extract(doc, model_path, **kwargs)


def extract_from_text(text, model_path, **kwargs):
    """ Extract keywords from a given text """
    doc = Document(0, None, text=text)
    return extract(doc, model_path, **kwargs)


def extract(doc, model_path, **kwargs):
    """
    Extract keywords from a given file
    :param doc: Document object
    # :param ontology_path: unicode with the ontology path
    :param model_path: unicode with the trained model path
    # :param recreate_ontology: boolean flag whether to recreate the ontology
    # :param verbose: whether to print additional info

    :return: set of predicted keywords
    """
    nn_name = os.path.basename(model_path).split('.')[0]
    model = get_nn_model(nn_name)
    model.load_weights(model_path)

    return nn_extract(doc, model, **kwargs)

    # ontology = get_ontology(path=ontology_path, recreate=recreate_ontology)
    # considered_keywords = set(get_considered_keywords())
    # inv_index = InvertedIndex(doc)
    #
    # # Load the model
    # model = load_from_disk(model_path)
    #
    # # Generate keyword candidates
    # kw_candidates = list(generate_keyword_candidates(doc, ontology))
    #
    # X = build_feature_matrix(kw_candidates, inv_index, model)
    #
    # # Predict
    # y_predicted = model.scale_and_predict(X)
    #
    # kw_predicted = []
    # for bit, kw in zip(y_predicted, kw_candidates):
    #     if bit == 1:
    #         kw_predicted.append(kw)
    #
    # # Print results
    # if verbose:
    #     print("Document content:")
    #     print(doc)
    #
    #     print("Predicted keywords:")
    #     for kw in kw_predicted:
    #         print(u"\t" + unicode(kw.get_canonical_form()))
    #     print()
    #
    #     answers = get_answers_for_doc(
    #         doc.filename,
    #         os.path.dirname(doc.filepath),
    #         filtered_by=considered_keywords,
    #     )
    #
    #     candidates = {kw.get_canonical_form() for kw in kw_candidates}
    #     print("Ground truth keywords:")
    #     for kw in answers:
    #         in_candidates = "(in candidates)" if kw in candidates else ""
    #         print("\t" + kw.ljust(30, ' ') + in_candidates)
    #     print()
    #
    #     y = []
    #     for kw in kw_candidates:
    #         y.append(1 if kw.get_canonical_form() in answers else 0)
    #
    #     X['name'] = [kw.get_canonical_form() for kw in kw_candidates]
    #     X['predicted'] = y_predicted
    #     X['ground truth'] = y
    #
    #     pd.set_option('expand_frame_repr', False)
    #     print(X[(X['ground truth'] == 1) | (X['predicted'])])
    #
    # return {kw.get_canonical_form() for kw in kw_predicted}


def test(
    testset_path=HEP_TEST_PATH,
    ontology=HEP_ONTOLOGY,
    model=MODEL_PATH,
    recreate_ontology=False,
    verbose=True,
):
    """
    Test the trained model on a set under a given path.
    :param testset_path: path to the directory with the test set
    :param ontology: path to the ontology
    :param model: path where the model is pickled
    :param recreate_ontology: boolean flag whether to recreate the ontology
    :param verbose: whether to print computation times

    :return tuple of three floats (precision, recall, f1_score)
    """
    if type(model) in [str, unicode]:
        model = load_from_disk(model)

    if type(ontology) in [str, unicode]:
        ontology = get_ontology(path=ontology, recreate=recreate_ontology)

    tick = time.clock()
    x, answers, kw_vector = build_test_matrices(
        get_documents(testset_path),
        model,
        testset_path,
        ontology,
    )
    if verbose:
        print("Matrices built in: {0:.2f}s".format(time.clock() - tick))

    # Predict
    y_pred = model.scale_and_predict_confidence(x)

    # Evaluate the results
    return evaluate_results(
        y_pred,
        kw_vector,
        answers,
    )


def batch_test(
    testset_path=HEP_TEST_PATH,
    batch_size=BATCH_SIZE,
    ontology=HEP_ONTOLOGY,
    model=MODEL_PATH,
    recreate_ontology=False,
    verbose=True,
):
    """
    Test the trained model on a set under a given path.
    :param testset_path: path to the directory with the test set
    :param batch_size: size of the testing batch
    :param ontology: path to the ontology
    :param model: path where the model is pickled
    :param recreate_ontology: boolean flag whether to recreate the ontology
    :param verbose: whether to print computation times

    :return tuple of three floats (precision, recall, f1_score)
    """
    if type(model) in [str, unicode]:
        model = load_from_disk(model)

    if type(ontology) in [str, unicode]:
        ontology = get_ontology(path=ontology, recreate=recreate_ontology)

    doc_generator = get_documents(testset_path, as_generator=True)
    start_time = time.clock()

    all_metrics = ['map', 'mrr', 'ndcg', 'r_prec', 'p_at_3', 'p_at_5']
    metrics_agg = {m: [] for m in all_metrics}

    if verbose:
        print("Batches:", end=' ')

    no_more_samples = False
    batch_number = 0
    while not no_more_samples:
        batch_number += 1

        batch = []
        for i in xrange(batch_size):
            try:
                batch.append(doc_generator.next())
            except StopIteration:
                no_more_samples = True
                break

        if not batch:
            break

        X, answers, kw_vector = build_test_matrices(
            batch,
            model,
            testset_path,
            ontology,
        )

        # Predict
        y_pred = model.scale_and_predict_confidence(X)

        # Evaluate the results
        metrics = evaluate_results(
            y_pred,
            kw_vector,
            answers,
        )
        for k, v in metrics.iteritems():
            metrics_agg[k].append(v)

        if verbose:
            sys.stdout.write(b'.')
            sys.stdout.flush()

    if verbose:
        print()
        print("Testing finished in: {0:.2f}s".format(time.clock() - start_time))

    return {k: np.mean(v) for k, v in metrics_agg.iteritems()}


def train(
    trainset_dir=HEP_TRAIN_PATH,
    word2vec_path=WORD2VEC_MODELPATH,
    ontology_path=HEP_ONTOLOGY,
    model_path=MODEL_PATH,
    recreate_ontology=False,
    verbose=True,
):
    """
    Train and save the model on a given dataset
    :param trainset_dir: path to the directory with the training set
    :param word2vec_path: path to the gensim word2vec model
    :param ontology_path: path to the ontology file
    :param model_path: path where the model should be pickled
    :param recreate_ontology: boolean flag whether to recreate the ontology
    :param verbose: whether to print computation times

    :return None if everything goes fine, error otherwise
    """
    ontology = get_ontology(path=ontology_path, recreate=recreate_ontology)
    docs = get_documents(trainset_dir)

    global_index = build_global_frequency_index(trainset_dir, verbose=verbose)
    word2vec_model = get_word2vec_model(word2vec_path, trainset_dir, verbose=verbose)
    model = LearningModel(global_index, word2vec_model)

    tick = time.clock()

    x, y = build_train_matrices(docs, model, trainset_dir, ontology)

    if verbose:
        print("Matrices built in: {0:.2f}s".format(time.clock() - tick))
    t1 = time.clock()

    if verbose:
        print("X size: {}".format(x.shape))

    # Normalize features
    x = model.maybe_fit_and_scale(x)

    # Train the model
    model.fit_classifier(x, y)

    if verbose:
        print("Fitting the model: {0:.2f}s".format(time.clock() - t1))

    # Pickle the model
    save_to_disk(model_path, model, overwrite=True)


def batch_train(
    trainset_dir=HEP_TRAIN_PATH,
    nb_epochs=NB_EPOCHS,
    batch_size=BATCH_SIZE,
    ontology_path=HEP_ONTOLOGY,
    model_path=MODEL_PATH,
    recreate_ontology=False,
    word2vec_path=WORD2VEC_MODELPATH,
    verbose=True,
):
    """
    Train and save the model on a given dataset
    :param trainset_dir: path to the directory with the training set
    :param nb_epochs: number of passes over the training set
    :param batch_size: the size of a single batch
    :param ontology_path: path to the ontology file
    :param model_path: path to the pickled LearningModel object
    :param word2vec_path: path to the gensim word2vec model
    :param recreate_ontology: boolean flag whether to recreate the ontology
    :param verbose: whether to print computation times

    :return None if everything goes fine, error otherwise
    """
    ontology = get_ontology(path=ontology_path, recreate=recreate_ontology, verbose=False)

    global_index = build_global_frequency_index(trainset_dir, verbose=False)
    word2vec_model = get_word2vec_model(word2vec_path, trainset_dir, verbose=False)
    model = LearningModel(global_index, word2vec_model)
    previous_best = -1

    for epoch in xrange(nb_epochs):
        doc_generator = get_documents(
            data_dir=trainset_dir,
            as_generator=True,
            shuffle=True,
        )
        epoch_start = time.clock()

        if verbose:
            print("Epoch {}".format(epoch + 1), end=' ')

        no_more_samples = False
        batch_number = 0
        while not no_more_samples:
            batch_number += 1

            batch = []
            for i in xrange(batch_size):
                try:
                    batch.append(doc_generator.next())
                except StopIteration:
                    no_more_samples = True
                    break

            if not batch:
                break

            x, y = build_train_matrices(batch, model, trainset_dir, ontology)

            # Normalize features
            # x = model.maybe_fit_and_scale(x)

            # Train the model
            model.partial_fit_classifier(x, y)

            if verbose:
                sys.stdout.write(b'.')
                sys.stdout.flush()

        if verbose:
            print(" {0:.2f}s".format(time.clock() - epoch_start))

        metrics = batch_test(model=model, ontology=ontology, verbose=False)

        for k, v in metrics.iteritems():
            print("{0}: {1}".format(k, v))

        if metrics['map'] > previous_best:
            previous_best = metrics['map']
            save_to_disk(model_path, model, overwrite=True)


if __name__ == '__main__':
    train()
