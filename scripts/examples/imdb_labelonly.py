# this script is used to test the classifier in semi-vae
from lasagne import layers
import semi_vae
import cPickle as pkl
import gzip
from theano import tensor as T
from lasagne import updates
import theano
import numpy as np
from batchiterator import *
from misc import *

def init_configurations():
    params = {}
    params['data'] = 'imdb'
    params['batch_size'] = 250
    params['num_classes'] = 10
    params['dim_z'] = 50
    params['num_units_hidden_common'] = 500
    params['num_samples_train_label'] = 1000 # the first n samples in trainset.
    params['epoch'] = 3000
    params['valid_period'] = 1 # temporary exclude validset
    params['test_period'] = 1
    params['alpha'] = 0.1
    return params


def load_data(params):
    if params['data'] == 'imdb':
        train, dev, test = load_imdb()


def build(params):
    image_shape = params['image_shape']
    image_layer = layers.InputLayer([params['batch_size'], image_shape[0] * image_shape[1]])
    label_layer = layers.InputLayer([params['batch_size'], params['num_classes']])

    # rewighted alpha
    reweighted_alpha = (params['alpha'] * params['num_samples_train'] / params['num_samples_train_label'])
    semi_vae_layer = semi_vae.SemiVAE(
        [image_layer, label_layer],
        params['num_units_hidden_common'],
        params['dim_z'],
        reweighted_alpha
    )

    sym_label_images = T.matrix('label_images')
    sym_label_labels = T.matrix('label_labels')
    sym_unlabel_images = T.matrix('unlabel_images')

    cost_for_label = semi_vae_layer.get_cost_for_label([sym_label_images, sym_label_labels])
    cost_for_unlabel = semi_vae_layer.get_cost_for_unlabel(sym_unlabel_images)
    cost_together = semi_vae_layer.get_cost_together([sym_label_images, sym_label_labels, sym_unlabel_images])
    cost_test, acc_test = semi_vae_layer.get_cost_test([sym_label_images, sym_label_labels])

    network_params = semi_vae_layer.get_params()

    for param in network_params:
        print(param, param.get_value().shape)

    update_for_label = updates.adam(cost_for_label, network_params)
    update_for_unlabel = updates.adam(cost_for_unlabel, network_params)
    update_together = updates.adam(cost_together, network_params, learning_rate=3e-4)

    fn_train = theano.function([sym_label_images, sym_label_labels, sym_unlabel_images],
                                cost_together,
                                updates = update_together,
                                on_unused_input = 'warn'
                                )
    '''
    fn_for_label = theano.function([sym_label_images, sym_label_labels], cost_for_label,
                                   updates = update_for_label,
                                   #on_unused_input = 'warn',
                                   )
    fn_for_unlabel = theano.function([sym_unlabel_images], cost_for_unlabel,
                                     updates = update_for_unlabel,
                                     #on_unused_input = 'warn'
                                     )
    '''
    fn_for_label = None
    fn_for_unlabel = None


    fn_for_test = theano.function([sym_label_images, sym_label_labels], [cost_test, acc_test])

    return semi_vae, fn_for_label, fn_for_unlabel, fn_train, fn_for_test


def train():
    params = init_configurations()
    trainset_label, trainset_unlabel, devset, testset = load_data_split(params, binarize_y = True)

    assert params['num_samples_train'] % params['batch_size'] == 0
    assert params['num_samples_dev'] % params['batch_size'] == 0
    assert params['num_samples_test'] % params['batch_size'] == 0

    num_batches_train = params['num_samples_train'] / params['batch_size']
    num_batches_dev = params['num_samples_dev'] / params['batch_size']
    num_batches_test = params['num_samples_test'] / params['batch_size']

    assert params['num_samples_train_label'] % num_batches_train == 0

    num_samples_per_batch_label = params['num_samples_train_label'] / num_batches_train
    num_samples_per_batch_unlabel = params['batch_size'] - num_samples_per_batch_label

    print(num_samples_per_batch_label)
    print(num_samples_per_batch_unlabel)
    print(params)

    iter_train_label = BatchIterator(range(params['num_samples_train_label']),
                                     num_samples_per_batch_label,
                                     data = trainset_label)

    num_samples_train_unlabel = params['num_samples_train'] - params['num_samples_train_label']
    iter_train_unlabel = BatchIterator(range(num_samples_train_unlabel),
                                        num_samples_per_batch_unlabel,
                                        data = trainset_unlabel)

    iter_test = BatchIterator(range(params['num_samples_test']),
                              params['batch_size'],
                              data = testset,
                              testing = True)

    # remain fn_for_label and fn_for_unlabel for testing
    semi_vea_layer, fn_for_label, fn_for_unlabel, fn_train, fn_for_test = build(params)

    for epoch in xrange(params['epoch']):
        #n_batches_train_label = params['num_samples_train_label']/params['batch_size']
        #n_batches_train_unlabel = (params['num_samples_train'] - params['num_samples_train_label'])/params['batch_size']

        #train_batch_costs_label = []
        #train_batch_costs_unlabel = []
        train_batch_costs = []
        for batch in xrange(num_batches_train):
        #for batch in xrange(1):
            #idx = idx_batches[batch]

            # for label
            #print('Training for label')
            label_images, label_labels = iter_train_label.next()
            unlabel_images, _ = iter_train_unlabel.next()
            #print label_images, label_labels, unlabel_images
            train_batch_cost = fn_train(label_images, label_labels, unlabel_images)
            train_batch_costs.append(train_batch_cost)

        print('TRAIN epoch %d: %f'%(epoch, np.mean(train_batch_costs)))

        #print('Epoch %d label %f unlabel %f' % (epoch, train_batch_mcost_label, train_batch_mcost_unlabel))

        if epoch % params['test_period'] == 0:
            num_batches_test = params['num_samples_test'] / params['batch_size']
            test_batch_costs = np.zeros([num_batches_test])
            test_batch_accs = np.zeros([num_batches_test])
            for batch in xrange(num_batches_test):
            #for batch in xrange(1):
                #print('Training for test')
                images, labels = iter_test.next()
                test_batch_cost, test_batch_acc = fn_for_test(images, labels)
                test_batch_costs[batch] = test_batch_cost
                test_batch_accs[batch] = test_batch_acc
                #print('TEST epoch %d batch %d: %f %f' % (epoch, batch, test_batch_cost, test_batch_acc))
            print('TEST epoch %d: %f %f' % (epoch, test_batch_costs.mean(), test_batch_accs.mean()))


if __name__ == '__main__':
    train()
