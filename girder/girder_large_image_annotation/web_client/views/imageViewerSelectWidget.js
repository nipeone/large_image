import _ from 'underscore';

import { wrap } from 'girder/utilities/PluginUtils';

import ImageViewerSelectWidget from '@girder/large_image/views/imageViewerSelectWidget';

import imageViewerAnnotationList from '../templates/imageViewerAnnotationList.pug';

import AnnotationListWidget from './annotationListWidget';

wrap(ImageViewerSelectWidget, 'initialize', function (initialize) {
    initialize.apply(this, _.rest(arguments));
    this._annotationList = new AnnotationListWidget({
        model: this.model,
        parentView: this
    });
});

wrap(ImageViewerSelectWidget, 'render', function (render) {
    render.apply(this, _.rest(arguments));
    this.$el.append(imageViewerAnnotationList());
    this._annotationList
        .setViewer(this.currentViewer)
        .setElement(this.$('.g-annotation-list-container'))
        .render();
    return this;
});

wrap(ImageViewerSelectWidget, '_selectViewer', function (_selectViewer) {
    _selectViewer.apply(this, _.rest(arguments));
    this._annotationList
        .setViewer(this.currentViewer)
        .render();
    return this;
});

export default ImageViewerSelectWidget;
