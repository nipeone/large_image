import _ from 'underscore';
import Backbone from 'backbone';
// Import hammerjs for geojs touch events
import Hammer from 'hammerjs';

import { staticRoot } from 'girder/rest';
import events from 'girder/events';

import ImageViewerWidget from './base';
import convertAnnotation from '../../annotations/geojs/convert';

window.hammerjs = Hammer;

/**
 * Generate a new "random" element id (24 random 16 digits).
 */
function guid() {
    function s4() {
        return Math.floor((1 + Math.random()) * 0x10000)
            .toString(16)
            .substring(1);
    }
    return s4() + s4() + s4() + s4() + s4() + s4();
}

var GeojsImageViewerWidget = ImageViewerWidget.extend({
    initialize: function (settings) {
        this._annotations = {};
        this._featureOpacity = {};
        this._highlightFeatureSizeLimit = settings.highlightFeatureSizeLimit || 10000;
        this.listenTo(events, 's:widgetDrawRegion', this.drawRegion);
        this.listenTo(events, 'g:startDrawMode', this.startDrawMode);
        this._hoverEvents = settings.hoverEvents;

        $.when(
            ImageViewerWidget.prototype.initialize.call(this, settings),
            $.ajax({ // like $.getScript, but allow caching
                url: staticRoot + '/built/plugins/large_image/extra/geojs.js',
                dataType: 'script',
                cache: true
            }))
            .done(() => {
                this.trigger('g:beforeFirstRender', this);
                this.render();
            });
    },

    render: function () {
        // If script or metadata isn't loaded, then abort
        if (!window.geo || !this.tileWidth || !this.tileHeight || this.deleted) {
            return this;
        }

        if (this.viewer) {
            // don't rerender the viewer
            return this;
        }

        var geo = window.geo; // this makes the style checker happy

        var params;
        if (!this.geospatial || !this.bounds) {
            var w = this.sizeX, h = this.sizeY;
            params = geo.util.pixelCoordinateParams(
                this.el, w, h, this.tileWidth, this.tileHeight);
            params.layer.useCredentials = true;
            params.layer.url = this._getTileUrl('{z}', '{x}', '{y}');
            this.viewer = geo.map(params.map);
            this.viewer.createLayer('osm', params.layer);
        } else {
            params = {
                keepLower: false,
                attribution: null,
                url: this._getTileUrl('{z}', '{x}', '{y}', {'encoding': 'PNG'}),
                useCredentials: true
            };
            this.viewer = geo.map({node: this.el});
            this.viewer.bounds({
                left: this.bounds.xmin,
                right: this.bounds.xmax,
                top: this.bounds.ymax,
                bottom: this.bounds.ymin
            }, 'EPSG:3857');
            this.viewer.createLayer('osm');
            this.viewer.createLayer('osm', params);
        }
        // the feature layer is for annotations that are loaded
        this.featureLayer = this.viewer.createLayer('feature', {
            features: ['point', 'line', 'polygon']
        });
        this.featureLayer.geoOn(window.geo.event.pan, () => { this.setBounds(); });
        // the annotation layer is for annotations that are actively drawn
        this.annotationLayer = this.viewer.createLayer('annotation', {
            annotations: ['point', 'line', 'rectangle', 'polygon'],
            showLabels: false
        });

        this.trigger('g:imageRendered', this);
        return this;
    },

    destroy: function () {
        if (this.viewer) {
            this.viewer.exit();
            this.viewer = null;
        }
        this.deleted = true;
        ImageViewerWidget.prototype.destroy.call(this);
    },

    /**
     * Render an annotation model on the image.  Currently,
     * this is limited to annotation types that can be directly
     * converted into geojson primatives.
     *
     * Internally, this generates a new feature layer for the
     * annotation that is referenced by the annotation id.
     * All "elements" contained inside this annotations are
     * drawn in the referenced layer.
     *
     * @param {AnnotationModel} annotation
     * @param {object} [options]
     * @param {boolean} [options.fetch=true]
     *   Enable fetching the annotation from the server, including paging
     *   the results.  If false, it is assumed the elements already
     *   exist on the annotation object.  This is useful for temporarily
     *   showing annotations that are not propagated to the server.
     */
    drawAnnotation: function (annotation, options) {
        var geo = window.geo;
        options = _.defaults(options || {}, {fetch: true});
        var geojson = annotation.geojson();
        var present = _.has(this._annotations, annotation.id);
        if (present) {
            _.each(this._annotations[annotation.id].features, (feature) => {
                this.featureLayer.deleteFeature(feature);
            });
        }
        this._annotations[annotation.id] = {
            features: [],
            options: options,
            annotation: annotation
        };
        if (options.fetch && !present) {
            annotation.off('g:fetched', null, this).on('g:fetched', () => {
                // Trigger an event indicating to the listener that
                // mouseover states should reset.
                this.trigger(
                    'g:mouseResetAnnotation',
                    annotation
                );
                this.drawAnnotation(annotation);
            }, this);
            this.setBounds({[annotation.id]: this._annotations[annotation.id]});
        }
        var featureList = this._annotations[annotation.id].features;
        this._featureOpacity[annotation.id] = {};
        window.geo.createFileReader('jsonReader', {layer: this.featureLayer})
            .read(geojson, (features) => {
                _.each(features || [], (feature) => {
                    var events = geo.event.feature;
                    featureList.push(feature);

                    feature.selectionAPI(this._hoverEvents);

                    feature.geoOn(
                        [
                            events.mouseclick,
                            events.mouseoff,
                            events.mouseon,
                            events.mouseover,
                            events.mouseout
                        ],
                        (evt) => this._onMouseFeature(evt)
                    );

                    // store the original opacities for the elements in each feature
                    const data = feature.data();
                    if (data.length <= this._highlightFeatureSizeLimit) {
                        this._featureOpacity[annotation.id][feature.featureType] = feature.data()
                            .map(({id, properties}) => {
                                return {
                                    id,
                                    fillOpacity: properties.fillOpacity,
                                    strokeOpacity: properties.strokeOpacity
                                };
                            });
                    }
                });
                this._mutateFeaturePropertiesForHighlight(annotation.id, features);
                this.viewer.draw();
            });
    },

    /**
     * Highlight the given annotation/element by reducing the opacity of all
     * other elements by 75%.  For performance reasons, features with a large
     * number of elements are not modified.  The limit for this behavior is
     * configurable via the constructor option `highlightFeatureSizeLimit`.
     *
     * Both arguments are optional.  If no element is provided, then all
     * elements in the given annotation are highlighted.  If no annotation
     * is provided, then highlighting state is reset and the original
     * opacities are used for all elements.
     *
     * @param {string?} annotation The id of the annotation to highlight
     * @param {string?} element The id of the element to highlight
     */
    highlightAnnotation: function (annotation, element) {
        this._highlightAnnotation = annotation;
        this._highlightElement = element;
        _.each(this._annotations, (layer, annotationId) => {
            const features = layer.features;
            this._mutateFeaturePropertiesForHighlight(annotationId, features);
        });
        this.viewer.draw();
        return this;
    },

    /**
     * Use geojs's `updateStyleFromArray` to modify the opacities of all elements
     * in a feature.  This method uses the private attributes `_highlightAnntotation`
     * and `_highlightElement` to determine which element to modify.
     */
    _mutateFeaturePropertiesForHighlight: function (annotationId, features) {
        _.each(features, (feature) => {
            const data = this._featureOpacity[annotationId][feature.featureType];
            if (!data) {
                // skip highlighting code on features with a lot of entities because
                // this slows down interactivity considerably.
                return;
            }
            const fillOpacityArray = [];
            const strokeOpacityArray = [];

            // pre-allocate arrays for performance
            fillOpacityArray.length = data.length;
            strokeOpacityArray.length = data.length;
            for (let i = 0; i < data.length; i += 1) {
                const id = data[i].id;
                const fillOpacity = data[i].fillOpacity;
                const strokeOpacity = data[i].strokeOpacity;
                if (!this._highlightAnnotation ||
                    (!this._highlightElement && annotationId === this._highlightAnnotation) ||
                    this._highlightElement === id) {
                    fillOpacityArray[i] = fillOpacity;
                    strokeOpacityArray[i] = strokeOpacity;
                } else {
                    fillOpacityArray[i] = fillOpacity * 0.25;
                    strokeOpacityArray[i] = strokeOpacity * 0.25;
                }
            }

            feature.updateStyleFromArray('fillOpacity', fillOpacityArray);
            feature.updateStyleFromArray('strokeOpacity', strokeOpacityArray);
        });
    },

    /**
     * When the image visible bounds change, or an annotation is first created,
     * set the view information for any annotation which requires it.
     *
     * @param {object} [annotations] If set, a dictionary where the keys are
     *      annotation ids and the values are an object which includes the
     *      annotation options and a reference to the annotation.  If not
     *      specified, use `this._annotations` and update the view for all
     *      relevant annotatioins.
     */
    setBounds: function (annotations) {
        var zoom = this.viewer.zoom(),
            bounds = this.viewer.bounds(),
            zoomRange = this.viewer.zoomRange();
        _.each(annotations || this._annotations, (annotation) => {
            if (annotation.options.fetch && annotation.annotation.setView) {
                annotation.annotation.setView(bounds, zoom, zoomRange.max);
            }
        });
    },

    /**
     * Remove an annotation from the image.  This simply
     * finds a layer with the given id and removes it because
     * each annotation is contained in its own layer.  If
     * the annotation is not drawn, this is a noop.
     *
     * @param {AnnotationModel} annotation
     */
    removeAnnotation: function (annotation) {
        annotation.off('g:fetched', null, this);
        // Trigger an event indicating to the listener that
        // mouseover states should reset.
        this.trigger(
            'g:mouseResetAnnotation',
            annotation
        );
        if (_.has(this._annotations, annotation.id)) {
            _.each(this._annotations[annotation.id].features, (feature) => {
                this.featureLayer.deleteFeature(feature);
            });
            delete this._annotations[annotation.id];
            delete this._featureOpacity[annotation.id];
            this.featureLayer.draw();
        }
    },

    /**
     * Set the image interaction mode to region drawing mode.  This
     * method takes an optional `model` argument where the region will
     * be stored when created by the user.  In any case, this method
     * returns a promise that resolves to an array defining the region:
     *   [ left, top, width, height ]
     *
     * @param {Backbone.Model} [model] A model to set the region to
     * @returns {$.Promise}
     */
    drawRegion: function (model) {
        model = model || new Backbone.Model();
        return this.startDrawMode('rectangle', {trigger: false}).then((elements) => {
            /*
             * Strictly speaking, the rectangle drawn here could be rotated, but
             * for simplicity we will set the region model assuming it is not.
             * To be more precise, we could expand the region to contain the
             * whole rotated rectangle.  A better solution would be to add
             * a draw parameter to geojs that draws a rectangle aligned with
             * the image coordinates.
             */
            var element = elements[0];
            var width = Math.round(element.width);
            var height = Math.round(element.height);
            var left = Math.round(element.center[0] - element.width / 2);
            var top = Math.round(element.center[1] - element.height / 2);

            model.set('value', [
                left, top, width, height
            ], {trigger: true});

            return model.get('value');
        });
    },

    /**
     * Set the image interaction mode to draw the given type of annotation.
     *
     * @param {string} type An annotation type, or null to turn off drawing.
     * @param {object} [options]
     * @param {boolean} [options.trigger=true]
     *      Trigger a global event after creating each annotation element.
     * @returns {$.Promise}
     *      Resolves to an array of generated annotation elements.
     */
    startDrawMode: function (type, options) {
        var layer = this.annotationLayer;
        var elements = [];
        var annotations = [];
        var defer = $.Deferred();
        var element;

        layer.mode(null);
        layer.geoOff(window.geo.event.annotation.state);
        layer.removeAllAnnotations();

        options = _.defaults(options || {}, {trigger: true});
        layer.geoOn(
            window.geo.event.annotation.state,
            (evt) => {
                if (evt.annotation.state() !== window.geo.annotation.state.done) {
                    return;
                }
                element = convertAnnotation(evt.annotation);
                if (!element.id) {
                    element.id = guid();
                }
                elements.push(element);
                annotations.push(evt.annotation);

                if (options.trigger) {
                    events.trigger('g:annotationCreated', element, evt.annotation);
                }

                layer.removeAllAnnotations();
                layer.geoOff(window.geo.event.annotation.state);
                defer.resolve(elements, annotations);
            }
        );
        layer.mode(type);
        return defer.promise();
    },

    _setEventTypes: function () {
        var events = window.geo.event.feature;
        this._eventTypes = {
            [events.mouseclick]: 'g:mouseClickAnnotation',
            [events.mouseoff]: 'g:mouseOffAnnotation',
            [events.mouseon]: 'g:mouseOnAnnotation',
            [events.mouseover]: 'g:mouseOverAnnotation',
            [events.mouseout]: 'g:mouseOutAnnotation'
        };
    },

    _onMouseFeature: function (evt) {
        var properties = evt.data.properties || {};
        var eventType;

        if (!this._eventTypes) {
            this._setEventTypes();
        }

        if (properties.element && properties.annotation) {
            eventType = this._eventTypes[evt.event];

            if (eventType) {
                this.trigger(
                    eventType,
                    properties.element,
                    properties.annotation
                );
            }
        }
    }
});

export default GeojsImageViewerWidget;
