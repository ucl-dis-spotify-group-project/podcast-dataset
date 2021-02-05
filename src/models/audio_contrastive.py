# -*- coding: utf-8 -*-

"""Self-supervised model for contrastive learning task."""

from json.decoder import JSONDecodeError
import os

import tensorflow as tf

import src.data as data
import src.models as models


class ContrastiveModel:
    """Provides functionality for self-supervised constrastive learning model."""

    def __init__(self, strategy, cfg):
        """Initializes a contrastive model object."""
        self._strategy = strategy
        self._ssl_dataset = cfg.ssl_dataset
        self._model_path = cfg.model_path
        self._experiment_id = cfg.experiment_id

        self._batch_size = cfg.batch_size
        self._epochs = cfg.epochs
        self._learning_rate = cfg.learning_rate
        self._temperature = cfg.temperature
        self._embedding_dim = cfg.embedding_dim
        self._similarity_type = cfg.similarity_type
        self._pooling_type = cfg.pooling_type
        self._noise = cfg.noise

        self._steps_per_epoch = cfg.steps_per_epoch
        self._shuffle_buffer = cfg.shuffle_buffer
        self._n_bands = cfg.n_bands
        self._n_channels = cfg.n_channels
        self._input_shape = (-1, None, self._n_bands, self._n_channels)

    def _get_ssl_task_data(self):
        """Prepares a dataset for contrastive self-supervised task."""
        if self._ssl_dataset == "podcasts":
            ds = data.get_podcast_dataset(
                method="sequential", data_path="/mnt/storage/cdtdisspotify/raw/"
            ).repeat()
        else:
            ds = data.get_tfds_dataset(self._ssl_dataset).repeat()
        ds = ds.batch(self._batch_size, drop_remainder=True)
        ds = ds.prefetch(tf.data.AUTOTUNE)
        return ds

    def train(self):
        """Trains a self-supervised model for contrastive learning."""
        train_dataset = self._get_ssl_task_data()
        train_dataset = self._strategy.experimental_distribute_dataset(train_dataset)

        with self._strategy.scope():
            contrastive_network = models.get_contrastive_network(
                embedding_dim=self._embedding_dim,
                temperature=self._temperature,
                pooling_type=self._pooling_type,
                similarity_type=self._similarity_type,
            )
            contrastive_network.compile(
                optimizer=tf.keras.optimizers.Adam(self._learning_rate),
                loss=tf.keras.losses.SparseCategoricalCrossentropy(from_logits=True),
                metrics=[tf.keras.metrics.SparseCategoricalAccuracy()],
            )

        ssl_model_dir = f"{self._ssl_dataset}/{self._experiment_id}/"
        ckpt_path = os.path.join(self._model_path, ssl_model_dir, "ckpt_{epoch}")
        model_checkpoint_callback = tf.keras.callbacks.ModelCheckpoint(
            filepath=ckpt_path, save_weights_only=True, monitor="loss"
        )

        backup_path = os.path.join(self._model_path, ssl_model_dir, "backup")
        backandrestore_callback = tf.keras.callbacks.experimental.BackupAndRestore(
            backup_dir=backup_path
        )

        log_dir = os.path.join(self._model_path, "log", self._experiment_id)
        tensorboard_callback = tf.keras.callbacks.TensorBoard(log_dir=log_dir)

        contrastive_network.fit(
            train_dataset,
            epochs=self._epochs,
            steps_per_epoch=self._steps_per_epoch,
            verbose=2,
            callbacks=[
                model_checkpoint_callback,
                backandrestore_callback,
                tensorboard_callback,
            ],
        )
