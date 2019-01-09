# -*- coding: utf-8 -*-

import numpy
import os
import PIL.Image
import pytest
import struct

from large_image import constants
import large_image_source_openslide

from . import utilities


def testTilesFromSVS():
    testDir = os.path.dirname(os.path.realpath(__file__))
    imagePath = os.path.join(testDir, 'test_files', 'yb10kx5k.png')
    assert large_image_source_openslide.OpenslideFileTileSource.canRead(imagePath) is False

    imagePath = utilities.externaldata(
        'data/sample_svs_image.TCGA-DU-6399-01A-01-TS1.e8eb65de-d63e-42db-'
        'af6f-14fefbbdf7bd.svs.sha512')
    assert large_image_source_openslide.OpenslideFileTileSource.canRead(imagePath) is True
    source = large_image_source_openslide.OpenslideFileTileSource(imagePath)
    tileMetadata = source.getMetadata()
    assert tileMetadata['tileWidth'] == 240
    assert tileMetadata['tileHeight'] == 240
    assert tileMetadata['sizeX'] == 31872
    assert tileMetadata['sizeY'] == 13835
    assert tileMetadata['levels'] == 9
    utilities.checkTilesZXY(source, tileMetadata)


def testMagnification():
    imagePath = utilities.externaldata(
        'data/sample_jp2k_33003_TCGA-CV-7242-11A-01-TS1.1838afb1-9eee-'
        '4a70-9ae3-50e3ab45e242.svs.sha512')
    source = large_image_source_openslide.OpenslideFileTileSource(imagePath)
    # tileMetadata = source.getMetadata()
    mag = source.getNativeMagnification()
    assert mag['magnification'] == 40.0
    assert mag['mm_x'] == 0.000252
    assert mag['mm_y'] == 0.000252
    mag = source.getMagnificationForLevel()
    assert mag['magnification'] == 40.0
    assert mag['mm_x'] == 0.000252
    assert mag['mm_y'] == 0.000252
    assert mag['level'] == 7
    assert mag['scale'] == 1.0
    mag = source.getMagnificationForLevel(0)
    assert mag['magnification'] == 0.3125
    assert mag['mm_x'] == 0.032256
    assert mag['mm_y'] == 0.032256
    assert mag['level'] == 0
    assert mag['scale'] == 128.0
    assert source.getLevelForMagnification() == 7
    assert source.getLevelForMagnification(exact=True) == 7
    assert source.getLevelForMagnification(40) == 7
    assert source.getLevelForMagnification(20) == 6
    assert source.getLevelForMagnification(0.3125) == 0
    assert source.getLevelForMagnification(15) == 6
    assert source.getLevelForMagnification(25) == 6
    assert source.getLevelForMagnification(15, rounding='ceil') == 6
    assert source.getLevelForMagnification(25, rounding='ceil') == 7
    assert source.getLevelForMagnification(15, rounding=False) == 5.585
    assert source.getLevelForMagnification(25, rounding=False) == 6.3219
    assert source.getLevelForMagnification(45, rounding=False) == 7
    assert source.getLevelForMagnification(15, rounding=None) == 5.585
    assert source.getLevelForMagnification(25, rounding=None) == 6.3219
    assert source.getLevelForMagnification(45, rounding=None) == 7.1699
    assert source.getLevelForMagnification(mm_x=0.0005) == 6
    assert source.getLevelForMagnification(mm_x=0.0005, mm_y=0.002) == 5
    assert source.getLevelForMagnification(mm_x=0.0005, exact=True) is None
    assert source.getLevelForMagnification(mm_x=0.000504, exact=True) == 6
    assert source.getLevelForMagnification(80) == 7
    assert source.getLevelForMagnification(80, exact=True) is None
    assert source.getLevelForMagnification(0.1) == 0


def testTileIterator():
    imagePath = utilities.externaldata(
        'data/sample_jp2k_33003_TCGA-CV-7242-11A-01-TS1.1838afb1-9eee-'
        '4a70-9ae3-50e3ab45e242.svs.sha512')
    source = large_image_source_openslide.OpenslideFileTileSource(imagePath)
    tileCount = 0
    visited = {}
    for tile in source.tileIterator(
            format=constants.TILE_FORMAT_PIL, scale={'magnification': 5}):
        # Check that we haven't loaded the tile's image yet
        assert not getattr(tile, 'loaded', None)
        visited.setdefault(tile['level_x'], {})[tile['level_y']] = True
        tileCount += 1
        assert tile['tile'].size == (tile['width'], tile['height'])
        assert tile['width'] == 256 if tile['level_x'] < 11 else 61
        assert tile['height'] == 256 if tile['level_y'] < 11 else 79
        # Check that we have loaded the tile's image
        assert getattr(tile, 'loaded', None) is True
    assert tileCount == 144
    assert len(visited) == 12
    assert len(visited[0]) == 12
    # Check with a non-native magnfication with exact=True
    tileCount = 0
    for tile in source.tileIterator(
            scale={'magnification': 4, 'exact': True}):
        tileCount += 1
    assert tileCount == 0
    # Check with a non-native (but factor of 2) magnfication with exact=True
    for tile in source.tileIterator(
            scale={'magnification': 2.5, 'exact': True}):
        tileCount += 1
    assert tileCount == 0
    # Check with a native magnfication with exact=True
    for tile in source.tileIterator(
            scale={'magnification': 5, 'exact': True}):
        tileCount += 1
    assert tileCount == 144
    # Check with a non-native magnfication without resampling
    tileCount = 0
    for tile in source.tileIterator(
            format=constants.TILE_FORMAT_PIL, scale={'magnification': 2}):
        tileCount += 1
        assert tile['tile'].size == (tile['width'], tile['height'])
        assert tile['width'] == 256 if tile['level_x'] < 11 else 61
        assert tile['height'] == 256 if tile['level_y'] < 11 else 79
    assert tileCount == 144
    # Check with a non-native magnfication with resampling
    tileCount = 0
    for tile in source.tileIterator(
            format=constants.TILE_FORMAT_PIL, scale={'magnification': 2}, resample=True):
        tileCount += 1
        assert tile['tile'].size == (tile['width'], tile['height'])
        assert tile['width'] == 256 if tile['level_x'] < 4 else 126
        assert tile['height'] == 256 if tile['level_y'] < 4 else 134
    assert tileCount == 25

    # Ask for numpy array as results
    tileCount = 0
    for tile in source.tileIterator(scale={'magnification': 5}):
        tileCount += 1
        assert isinstance(tile['tile'], numpy.ndarray)
        assert tile['tile'].shape == (
            256 if tile['level_y'] < 11 else 79,
            256 if tile['level_x'] < 11 else 61,
            4)
        assert tile['tile'].dtype == numpy.dtype('uint8')
    assert tileCount == 144
    # Ask for either PIL or IMAGE data, we should get PIL data
    tileCount = 0
    for tile in source.tileIterator(
            scale={'magnification': 5},
            format=(constants.TILE_FORMAT_PIL,
                    constants.TILE_FORMAT_IMAGE),
            encoding='JPEG'):
        tileCount += 1
        assert isinstance(tile['tile'], PIL.Image.Image)
    assert tileCount == 144
    # Ask for PNGs
    tileCount = 0
    for tile in source.tileIterator(
            scale={'magnification': 5},
            format=constants.TILE_FORMAT_IMAGE,
            encoding='PNG'):
        tileCount += 1
        assert not isinstance(tile['tile'], PIL.Image.Image)
        assert tile['tile'][:len(utilities.PNGHeader)] == utilities.PNGHeader
    assert tileCount == 144


def testGetRegion():
    imagePath = utilities.externaldata(
        'data/sample_jp2k_33003_TCGA-CV-7242-11A-01-TS1.1838afb1-9eee-'
        '4a70-9ae3-50e3ab45e242.svs.sha512')
    source = large_image_source_openslide.OpenslideFileTileSource(imagePath)
    # By default, getRegion gets an image
    image, mimeType = source.getRegion(scale={'magnification': 2.5})
    assert mimeType == 'image/jpeg'
    assert image[:len(utilities.JPEGHeader)] == utilities.JPEGHeader

    # Adding a tile position request should be ignored
    image2, imageFormat = source.getRegion(scale={'magnification': 2.5},
                                           tile_position=1)
    assert image == image2

    # We should be able to get a NUMPY array instead
    image, imageFormat = source.getRegion(
        scale={'magnification': 2.5},
        format=constants.TILE_FORMAT_NUMPY)
    assert imageFormat == constants.TILE_FORMAT_NUMPY
    assert isinstance(image, numpy.ndarray)
    assert image.shape == (1447, 1438, 4)

    # We should be able to get a PIL image
    image, imageFormat = source.getRegion(
        scale={'magnification': 2.5},
        format=(constants.TILE_FORMAT_PIL, constants.TILE_FORMAT_NUMPY))
    assert imageFormat == constants.TILE_FORMAT_PIL
    assert image.width == 1438
    assert image.height == 1447


def testConvertRegionScale():
    imagePath = utilities.externaldata(
        'data/sample_jp2k_33003_TCGA-CV-7242-11A-01-TS1.1838afb1-9eee-'
        '4a70-9ae3-50e3ab45e242.svs.sha512')
    source = large_image_source_openslide.OpenslideFileTileSource(imagePath)
    # If we aren't using pixels as our units and don't specify a target
    # unit, this should do nothing.  This source image is 23021 x 23162
    sourceRegion = {'width': 0.8, 'height': 0.7, 'units': 'fraction'}
    targetRegion = source.convertRegionScale(sourceRegion)
    assert sourceRegion == targetRegion

    # Units must be valid
    with pytest.raises(ValueError):
        source.convertRegionScale({'units': 'unknown'})
    with pytest.raises(ValueError):
        source.convertRegionScale(sourceRegion, targetUnits='unknown')

    # We can convert to pixels
    targetRegion = source.convertRegionScale(
        sourceRegion, targetScale={'magnification': 2.5},
        targetUnits='pixels')
    assert int(targetRegion['width']) == 1151
    assert int(targetRegion['height']) == 1013
    assert targetRegion['units'] == 'mag_pixels'

    # Now use that to convert to a different magnification
    sourceRegion = targetRegion
    sourceScale = {'magnification': 2.5}

    # Test other conversions
    targetScale = {'magnification': 1.25}
    targetRegion = source.convertRegionScale(
        sourceRegion, sourceScale, targetScale)
    assert int(targetRegion['width']) == 18417
    assert int(targetRegion['height']) == 16213
    assert targetRegion['units'] == 'base_pixels'

    targetRegion = source.convertRegionScale(
        sourceRegion, sourceScale, targetScale, targetUnits='fraction')
    assert targetRegion['width'] == pytest.approx(0.8, 1.0e-4)
    assert targetRegion['height'] == pytest.approx(0.7, 1.0e-4)
    assert targetRegion['units'] == 'fraction'

    targetRegion = source.convertRegionScale(
        sourceRegion, sourceScale, targetScale, targetUnits='mm')
    assert targetRegion['width'] == pytest.approx(4.6411, 1.0e-3)
    assert targetRegion['height'] == pytest.approx(4.0857, 1.0e-3)
    assert targetRegion['units'] == 'mm'

    targetRegion = source.convertRegionScale(
        sourceRegion, sourceScale, None, targetUnits='mm')
    assert targetRegion['width'] == pytest.approx(4.6411, 1.0e-3)
    assert targetRegion['height'] == pytest.approx(4.0857, 1.0e-3)
    assert targetRegion['units'] == 'mm'

    targetRegion = source.convertRegionScale(
        sourceRegion, sourceScale, targetScale, targetUnits='pixels')
    assert int(targetRegion['width']) == 575
    assert int(targetRegion['height']) == 506
    assert targetRegion['units'] == 'mag_pixels'

    # test getRegionAtAnotherScale
    image, imageFormat = source.getRegionAtAnotherScale(
        sourceRegion, sourceScale, targetScale,
        format=constants.TILE_FORMAT_NUMPY)
    assert imageFormat == constants.TILE_FORMAT_NUMPY
    assert isinstance(image, numpy.ndarray)
    assert image.shape == (506, 575, 4)
    with pytest.raises(TypeError):
        source.getRegionAtAnotherScale(
            sourceRegion, sourceScale, region=sourceRegion,
            format=constants.TILE_FORMAT_NUMPY)

    # test tileIteratorAtAnotherScale
    tileCount = 0
    for tile in source.tileIteratorAtAnotherScale(
            sourceRegion, sourceScale, targetScale,
            format=constants.TILE_FORMAT_NUMPY):
        tileCount += 1
    assert tileCount == 72
    with pytest.raises(TypeError):
        for tile in source.tileIteratorAtAnotherScale(
                sourceRegion, sourceScale, region=sourceRegion,
                format=constants.TILE_FORMAT_NUMPY):
            tileCount += 1


def testConvertPointScale():
    imagePath = utilities.externaldata(
        'data/sample_jp2k_33003_TCGA-CV-7242-11A-01-TS1.1838afb1-9eee-'
        '4a70-9ae3-50e3ab45e242.svs.sha512')
    source = large_image_source_openslide.OpenslideFileTileSource(imagePath)
    point = source.getPointAtAnotherScale((500, 800), {'magnification': 5}, 'mag_pixels')
    assert point == (4000.0, 6400.0)
    point = source.getPointAtAnotherScale(
        (500, 800), targetScale={'magnification': 5}, targetUnits='mag_pixels')
    assert point == (62.5, 100.0)
    point = source.getPointAtAnotherScale(
        (500000, 800), {'magnification': 5}, 'mag_pixels',
        {'magnification': 20}, 'mag_pixels')
    assert point == (2000000.0, 3200.0)


def testGetPixel():
    imagePath = utilities.externaldata(
        'data/sample_jp2k_33003_TCGA-CV-7242-11A-01-TS1.1838afb1-9eee-'
        '4a70-9ae3-50e3ab45e242.svs.sha512')
    source = large_image_source_openslide.OpenslideFileTileSource(imagePath)

    pixel = source.getPixel(region={'left': 12125, 'top': 10640})
    assert pixel == {'r': 156, 'g': 98, 'b': 138, 'a': 255}

    pixel = source.getPixel(region={'left': 3.0555, 'top': 2.68128, 'units': 'mm'})
    assert pixel == {'r': 156, 'g': 98, 'b': 138, 'a': 255}

    pixel = source.getPixel(region={'top': 10640, 'right': 12126, 'bottom': 12000})
    assert pixel == {'r': 156, 'g': 98, 'b': 138, 'a': 255}

    pixel = source.getPixel(region={'left': 12125, 'top': 10640, 'right': 13000})
    assert pixel == {'r': 156, 'g': 98, 'b': 138, 'a': 255}

    pixel = source.getPixel(region={'left': 12125, 'top': 10640}, includeTileRecord=True)
    assert 'tile' in pixel


def testTilesFromPowerOf3Tiles():
    imagePath = utilities.externaldata('data/G10-3_pelvis_crop-powers-of-3.tif.sha512')
    source = large_image_source_openslide.OpenslideFileTileSource(imagePath)
    tileMetadata = source.getMetadata()
    assert tileMetadata['tileWidth'] == 128
    assert tileMetadata['tileHeight'] == 128
    assert tileMetadata['sizeX'] == 3000
    assert tileMetadata['sizeY'] == 5000
    assert tileMetadata['levels'] == 7
    utilities.checkTilesZXY(source, tileMetadata)


def testRegionsWithMagnification():
    imagePath = utilities.externaldata(
        'data/sample_svs_image.TCGA-DU-6399-01A-01-TS1.e8eb65de-d63e-42db-'
        'af6f-14fefbbdf7bd.svs.sha512')
    source = large_image_source_openslide.OpenslideFileTileSource(imagePath)
    params = {'region': {'width': 2000, 'height': 1500},
              'output': {'maxWidth': 1000, 'maxHeight': 1000},
              'encoding': 'PNG'}
    image, mimeType = source.getRegion(**params)
    assert image[:len(utilities.PNGHeader)] == utilities.PNGHeader
    (width, height) = struct.unpack('!LL', image[16:24])
    assert width == 1000
    assert height == 750

    # test magnification
    params = {'region': {'width': 2000, 'height': 1500},
              'scale': {'magnification': 15},
              'encoding': 'PNG'}
    image, mimeType = source.getRegion(**params)
    assert image[:len(utilities.PNGHeader)] == utilities.PNGHeader
    (width, height) = struct.unpack('!LL', image[16:24])
    assert width == 750
    assert height == 562

    # test magnification with exact requirements
    params = {'region': {'width': 2000, 'height': 1500},
              'scale': {'magnification': 15, 'exact': True},
              'encoding': 'PNG'}
    image, mimeType = source.getRegion(**params)
    assert len(image) == 0

    params = {'region': {'width': 2000, 'height': 1500},
              'scale': {'magnification': 10, 'exact': True},
              'encoding': 'PNG'}
    image, mimeType = source.getRegion(**params)
    assert image[:len(utilities.PNGHeader)] == utilities.PNGHeader
    (width, height) = struct.unpack('!LL', image[16:24])
    assert width == 500
    assert height == 375


def testTilesAssociatedImages():
    imagePath = utilities.externaldata(
        'data/sample_svs_image.TCGA-DU-6399-01A-01-TS1.e8eb65de-d63e-42db-'
        'af6f-14fefbbdf7bd.svs.sha512')
    source = large_image_source_openslide.OpenslideFileTileSource(imagePath)
    imageList = source.getAssociatedImagesList()
    assert imageList == ['label', 'macro', 'thumbnail']
    image, mimeType = source.getAssociatedImage('macro')
    assert image[:len(utilities.JPEGHeader)] == utilities.JPEGHeader
    # Test missing associated image
    assert source.getAssociatedImage('nosuchimage') is None


def testTilesFromSmallFile():
    testDir = os.path.dirname(os.path.realpath(__file__))
    # Using a two-channel luminance-alpha tiff should work
    imagePath = os.path.join(testDir, 'test_files', 'small_la.tiff')
    source = large_image_source_openslide.OpenslideFileTileSource(imagePath)
    tileMetadata = source.getMetadata()
    assert tileMetadata['tileWidth'] == 2
    assert tileMetadata['tileHeight'] == 1
    assert tileMetadata['sizeX'] == 2
    assert tileMetadata['sizeY'] == 1
    assert tileMetadata['levels'] == 1
    utilities.checkTilesZXY(source, tileMetadata)
