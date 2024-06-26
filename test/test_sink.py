import large_image_source_test
import large_image_source_zarr
import numpy as np
import pytest

import large_image
from large_image.tilesource.resample import ResampleMethod

TMP_DIR = 'tmp/zarr_sink'
FILE_TYPES = [
    'tiff',
    'sqlite',
    'db',
    'zip',
    'zarr',
]


def copyFromSource(source, sink):
    metadata = source.getMetadata()
    for frame in metadata.get('frames', []):
        for tile in source.tileIterator(frame=frame['Frame'], format='numpy'):
            t = tile['tile']
            x, y = tile['x'], tile['y']
            kwargs = {
                'z': frame['IndexZ'],
                'c': frame['IndexC'],
            }
            sink.addTile(t, x=x, y=y, **kwargs)


def testNew():
    sink = large_image_source_zarr.new()
    assert sink.metadata['levels'] == 0
    assert sink.getRegion(format='numpy')[0].shape[:2] == (0, 0)


def testBasicAddTile():
    sink = large_image_source_zarr.new()
    sink.addTile(np.random.random((10, 10)), 0, 0)
    sink.addTile(np.random.random((10, 10, 2)), 10, 0)

    metadata = sink.getMetadata()
    assert metadata.get('levels') == 1
    assert metadata.get('sizeX') == 20
    assert metadata.get('sizeY') == 10
    assert metadata.get('bandCount') == 2
    assert metadata.get('dtype') == 'float64'


def testAddTileWithMask():
    sink = large_image_source_zarr.new()
    tile0 = np.random.random((10, 10))
    sink.addTile(tile0, 0, 0)
    orig = sink.getRegion(format='numpy')[0]
    tile1 = np.random.random((10, 10))
    sink.addTile(tile1, 0, 0, mask=np.random.random((10, 10)) > 0.5)
    cur = sink.getRegion(format='numpy')[0]
    assert (tile0 == orig[:, :, 0]).all()
    assert not (tile1 == orig[:, :, 0]).all()
    assert not (tile0 == cur[:, :, 0]).all()
    assert not (tile1 == cur[:, :, 0]).all()


def testAddTileWithLevel():
    sink = large_image_source_zarr.new()
    tile0 = np.random.random((100, 100))
    sink.addTile(tile0, 0, 0)
    arrays = dict(sink._zarr.arrays())
    assert arrays.get('0') is not None
    assert arrays.get('0').shape == (100, 100, 1)

    tile1 = np.random.random((10, 10))
    sink.addTile(tile1, 0, 0, level=1)
    arrays = dict(sink._zarr.arrays())
    assert arrays.get('0') is not None
    assert arrays.get('0').shape == (100, 100, 1)
    assert arrays.get('1') is not None
    assert arrays.get('1').shape == (10, 10, 1)

    tile1 = np.random.random((100, 100))
    sink.addTile(tile1, 0, 100)
    arrays = dict(sink._zarr.arrays())
    assert arrays.get('0') is not None
    assert arrays.get('0').shape == (200, 100, 1)
    # previously written levels should be cleared after changing level 0 data
    assert arrays.get('1') is None


def testExtraAxis():
    sink = large_image_source_zarr.new()
    sink.addTile(np.random.random((256, 256)), 0, 0, z=1)
    metadata = sink.getMetadata()
    assert metadata.get('bandCount') == 1
    assert len(metadata.get('frames')) == 2


@pytest.mark.parametrize('file_type', FILE_TYPES)
def testCrop(file_type, tmp_path):
    output_file = tmp_path / f'test.{file_type}'
    sink = large_image_source_zarr.new()

    # add tiles with some overlap
    sink.addTile(np.random.random((10, 10)), 0, 0)
    sink.addTile(np.random.random((10, 10)), 8, 0)
    sink.addTile(np.random.random((10, 10)), 0, 8)
    sink.addTile(np.random.random((10, 10)), 8, 8)

    region, _ = sink.getRegion(format='numpy')
    shape = region.shape
    assert shape == (18, 18, 1)

    sink.crop = (2, 2, 10, 10)

    # crop only applies when using write
    sink.write(output_file)
    if file_type == 'zarr':
        output_file /= '.zattrs'
    written = large_image.open(output_file)
    region, _ = written.getRegion(format='numpy')
    shape = region.shape
    assert shape == (10, 10, 1)


@pytest.mark.parametrize('file_type', FILE_TYPES)
def testImageCopySmallFileTypes(file_type, tmp_path):
    output_file = tmp_path / f'test.{file_type}'
    sink = large_image_source_zarr.new()
    source = large_image_source_test.TestTileSource(
        fractal=True,
        tileWidth=128,
        tileHeight=128,
        sizeX=512,
        sizeY=1024,
        frames='c=2,z=3',
    )
    copyFromSource(source, sink)

    metadata = sink.getMetadata()
    assert metadata.get('sizeX') == 512
    assert metadata.get('sizeY') == 1024
    assert metadata.get('dtype') == 'uint8'
    assert metadata.get('levels') == 2
    assert metadata.get('bandCount') == 3
    assert len(metadata.get('frames')) == 6

    sink.write(output_file)
    if file_type == 'zarr':
        output_file /= '.zattrs'
    written = large_image.open(output_file)

    new_metadata = written.getMetadata()
    assert new_metadata.get('sizeX') == 512
    assert new_metadata.get('sizeY') == 1024
    assert new_metadata.get('dtype') == 'uint8'
    assert new_metadata.get('levels') == 2 or new_metadata.get('levels') == 3
    assert new_metadata.get('bandCount') == 3
    assert len(new_metadata.get('frames')) == 6


@pytest.mark.parametrize('resample_method', [
    ResampleMethod.PIL_LANCZOS,
    ResampleMethod.NP_NEAREST,
])
def testImageCopySmallMultiband(resample_method, tmp_path):
    output_file = tmp_path / f'test_{resample_method}.db'
    sink = large_image_source_zarr.new()
    bands = (
        'red=0-255,green=0-255,blue=0-255,'
        'ir1=0-255,ir2=0-255,gray=0-255,other=0-255'
    )
    source = large_image_source_test.TestTileSource(
        fractal=True,
        tileWidth=128,
        tileHeight=128,
        sizeX=512,
        sizeY=1024,
        frames='c=2,z=3',
        bands=bands,
    )
    copyFromSource(source, sink)

    metadata = sink.getMetadata()
    assert metadata.get('sizeX') == 512
    assert metadata.get('sizeY') == 1024
    assert metadata.get('dtype') == 'uint8'
    assert metadata.get('levels') == 2
    assert metadata.get('bandCount') == 7
    assert len(metadata.get('frames')) == 6

    sink.write(output_file, resample=resample_method)
    written = large_image.open(output_file)
    new_metadata = written.getMetadata()

    assert new_metadata.get('sizeX') == 512
    assert new_metadata.get('sizeY') == 1024
    assert new_metadata.get('dtype') == 'uint8'
    assert new_metadata.get('levels') == 2 or new_metadata.get('levels') == 3
    assert new_metadata.get('bandCount') == 7
    assert len(new_metadata.get('frames')) == 6

    written_arrays = dict(written._zarr.arrays())
    assert len(written_arrays) == written.levels
    assert written_arrays.get('0') is not None
    assert written_arrays.get('0').shape == (2, 3, 1024, 512, 7)
    assert written_arrays.get('1') is not None
    assert written_arrays.get('1').shape == (2, 3, 512, 256, 7)


@pytest.mark.parametrize('resample_method', list(ResampleMethod))
def testImageCopySmallDownsampling(resample_method, tmp_path):
    output_file = tmp_path / f'test_{resample_method}.db'
    sink = large_image_source_zarr.new()
    source = large_image_source_test.TestTileSource(
        fractal=True,
        tileWidth=128,
        tileHeight=128,
        sizeX=511,
        sizeY=1023,
        frames='c=2,z=3',
    )
    copyFromSource(source, sink)

    sink.write(output_file, resample=resample_method)
    written = large_image.open(output_file)

    written_arrays = dict(written._zarr.arrays())
    assert len(written_arrays) == written.levels
    assert written_arrays.get('0') is not None
    assert written_arrays.get('0').shape == (2, 3, 1023, 511, 3)
    assert written_arrays.get('1') is not None
    assert written_arrays.get('1').shape == (2, 3, 512, 256, 3)

    sample_region, _format = written.getRegion(
        region=dict(top=252, bottom=260, left=0, right=4),
        output=dict(maxWidth=2, maxHeight=4),
        format='numpy',
    )
    assert sample_region.shape == (4, 2, 3)
    white_mask = (sample_region[..., 0] == 255).flatten().tolist()

    expected_masks = {
        ResampleMethod.PIL_NEAREST: [
            # expect any of the four variations, this will depend on version
            [True, False, True, False, True, True, True, False],  # upper left
            [True, False, True, True, True, False, True, False],  # lower left
            [True, False, False, True, True, True, False, False],  # upper right
            [False, False, True, True, False, True, True, False],  # lower right
        ],
        ResampleMethod.PIL_LANCZOS:
        [[False, False, False, False, False, False, False, False]],
        ResampleMethod.PIL_BILINEAR:
        [[False, False, False, False, False, False, False, False]],
        ResampleMethod.PIL_BICUBIC:
        [[False, False, False, False, False, False, False, False]],
        ResampleMethod.PIL_BOX:
        [[False, False, False, False, False, False, False, False]],
        ResampleMethod.PIL_HAMMING:
        [[False, False, False, False, False, False, False, False]],
        ResampleMethod.NP_MEAN:
        [[False, False, False, False, False, False, False, False]],
        ResampleMethod.NP_MEDIAN:
        [[True, False, True, True, True, True, True, False]],
        ResampleMethod.NP_MODE:
        [[True, False, True, True, True, True, True, False]],
        ResampleMethod.NP_MAX:
        [[True, False, True, True, True, True, True, False]],
        ResampleMethod.NP_MIN:
        [[False, False, False, False, False, False, False, False]],
        ResampleMethod.NP_NEAREST:
        [[True, False, True, False, True, True, True, False]],
        ResampleMethod.NP_MAX_COLOR:
        [[True, False, True, True, True, True, True, False]],
        ResampleMethod.NP_MIN_COLOR:
        [[False, False, False, False, False, False, False, False]],
    }

    assert white_mask in expected_masks[resample_method]


def testCropAndDownsample(tmp_path):
    output_file = tmp_path / 'cropped.db'
    sink = large_image_source_zarr.new()

    # add tiles with some overlap to multiple frames
    num_frames = 4
    num_bands = 5
    for z in range(num_frames):
        sink.addTile(np.random.random((1000, 1000, num_bands)), 0, 0, z=z)
        sink.addTile(np.random.random((1000, 1000, num_bands)), 950, 0, z=z)
        sink.addTile(np.random.random((1000, 1000, num_bands)), 0, 900, z=z)
        sink.addTile(np.random.random((1000, 1000, num_bands)), 950, 900, z=z)

    current_arrays = dict(sink._zarr.arrays())
    assert len(current_arrays) == 1
    assert current_arrays.get('0') is not None
    assert current_arrays.get('0').shape == (num_frames, 1900, 1950, num_bands)

    sink.crop = (50, 100, 1825, 1800)
    sink.write(output_file)
    written = large_image_source_zarr.open(output_file)
    written_arrays = dict(written._zarr.arrays())

    assert len(written_arrays) == written.levels
    assert written_arrays.get('0') is not None
    assert written_arrays.get('0').shape == (num_frames, 1800, 1825, num_bands)
    assert written_arrays.get('1') is not None
    assert written_arrays.get('1').shape == (num_frames, 900, 913, num_bands)
    assert written_arrays.get('2') is not None
    assert written_arrays.get('2').shape == (num_frames, 450, 456, num_bands)


def testCropToTiff(tmp_path):
    output_file = tmp_path / 'cropped.tiff'
    sink = large_image_source_zarr.new()

    # add tiles with some overlap to multiple frames
    num_frames = 1
    num_bands = 3
    for z in range(num_frames):
        sink.addTile(np.random.random((1000, 1000, num_bands)), 0, 0, z=z)
        sink.addTile(np.random.random((1000, 1000, num_bands)), 950, 0, z=z)
        sink.addTile(np.random.random((1000, 1000, num_bands)), 0, 900, z=z)
        sink.addTile(np.random.random((1000, 1000, num_bands)), 950, 900, z=z)

    current_arrays = dict(sink._zarr.arrays())
    assert len(current_arrays) == 1
    assert current_arrays.get('0') is not None
    assert current_arrays.get('0').shape == (num_frames, 1900, 1950, num_bands)

    sink.crop = (100, 50, 1800, 1825)
    sink.write(output_file)
    source = large_image.open(output_file)
    assert source.sizeX == 1800
    assert source.sizeY == 1825
