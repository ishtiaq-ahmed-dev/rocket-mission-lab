import json

import numpy as np
import pytest
import torch

from scripts.flight_policy import train


def rows(count):
    data = np.zeros((count, train.ROW), dtype=np.float32)
    data[:, train.B_VALID] = 1
    data[:, train.U_VALID] = 1
    data[:, train.B_X:train.B_X + train.NB] = np.arange(count)[:, None]
    return data


def test_file_backed_batches_preserve_shuffled_order_and_duplicates(tmp_path):
    a, b = rows(4), rows(3)
    b[:, train.B_X] += 10
    a.tofile(tmp_path / 'a.f32')
    b.tofile(tmp_path / 'b.f32')
    data, _ = train.load(tmp_path)
    assert all(isinstance(x, np.memmap) for x in data.arrays)
    indices = [6, 0, 4, 4, 2]
    expected = np.concatenate([a, b])[indices]
    np.testing.assert_array_equal(data.take(indices), expected)
    mean, std = train.mapped_normalizer(data, data.valid_indices(train.B_VALID), train.B_X, train.NB)
    expected_mean, expected_std = train.normalizer(np.concatenate([a, b])[:, train.B_X:train.B_X + train.NB])
    np.testing.assert_allclose(mean, expected_mean, atol=1e-6)
    np.testing.assert_allclose(std, expected_std, atol=1e-6)
    with pytest.raises(IndexError):
        data.take([len(data)])


@pytest.mark.parametrize('bad', ['empty', 'partial', 'nan', 'mode', 'engine'])
def test_invalid_datasets_fail_before_training(tmp_path, bad):
    data = rows(2)
    if bad == 'nan':
        data[0, 1] = np.nan
    elif bad == 'mode':
        data[0, train.B_MODE] = -1
    elif bad == 'engine':
        data[0, train.B_ENG] = 0.5
    if bad == 'empty':
        (tmp_path / 'bad.f32').write_bytes(b'')
    elif bad == 'partial':
        (tmp_path / 'bad.f32').write_bytes(b'abc')
    else:
        data.tofile(tmp_path / 'bad.f32')
    with pytest.raises(ValueError):
        train.load(tmp_path)


def test_resume_uses_exported_policy_weights_instead_of_an_unrelated_checkpoint(tmp_path):
    torch.manual_seed(7)
    booster, upper = train.mlp(train.NB, 256, 3, 9), train.mlp(train.NU, 128, 3, 7)
    spec = {'booster': train.export(booster, np.zeros(train.NB), np.ones(train.NB)),
            'upper': train.export(upper, np.zeros(train.NU), np.ones(train.NU))}
    file = tmp_path / 'candidate.js'
    file.write_text('(function(r){r.FLIGHT_POLICY=' + json.dumps(spec) + ';})(globalThis);')
    checkpoint = train.from_policy(file)
    for key, value in booster.state_dict().items():
        assert torch.equal(value, checkpoint['nb'][key])
    for key, value in upper.state_dict().items():
        assert torch.equal(value, checkpoint['nu'][key])


def test_failed_export_preserves_previous_policy(tmp_path):
    file = tmp_path / 'policy.js'
    file.write_text('previous')
    def broken(temporary):
        with open(temporary, 'w') as stream:
            stream.write('partial')
        raise OSError('interrupted')
    with pytest.raises(OSError, match='interrupted'):
        train.atomic_save(file, broken)
    assert file.read_text() == 'previous'
    assert list(tmp_path.iterdir()) == [file]
