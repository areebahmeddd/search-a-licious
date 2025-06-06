import {LitElement} from 'lit';
import {
  addParamPrefixes,
  removeParamPrefixes,
  removeParenthesis,
} from '../utils/url';
import {isNullOrUndefined} from '../utils';
import {SearchParameters} from '../interfaces/search-params-interfaces';
import {property} from 'lit/decorators.js';
import {QueryOperator} from '../utils/enums';
import {
  HistoryOutput,
  HistoryParams,
  HistorySearchParams,
  SearchaliciousHistoryInterface,
} from '../interfaces/history-interfaces';
import {SearchaliciousSort} from '../search-sort';
import {SearchaliciousFacets} from '../search-facets';
import {Constructor} from './utils';
import {DEFAULT_SEARCH_NAME} from '../utils/constants';

// name of search params as an array (to ease iteration)
export const SEARCH_PARAMS = Object.values(HistorySearchParams);

/**
 * Object to convert the URL params to the original values
 *
 * It maps parameter names to a function to transforms it to a JS value
 */
const HISTORY_VALUES: Record<
  HistorySearchParams,
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  (history: Record<string, string>) => Record<string, any>
> = {
  [HistorySearchParams.PAGE]: (history) =>
    history.page
      ? {
          page: parseInt(history.page),
        }
      : {},
  [HistorySearchParams.QUERY]: (history) => {
    // Avoid empty query but allow empty string
    if (isNullOrUndefined(history.q)) {
      return {};
    }
    return {
      query: history.q,
    };
  },
  [HistorySearchParams.SORT_BY]: (history) => {
    // in sort by we simply put the sort option id, so it's trivial
    return {
      sortOptionId: history.sort_by,
    };
  },
  // NOTE: this approach is a bit brittle,
  // shan't we instead store selected facets in the URL directly?
  [HistorySearchParams.FACETS_FILTERS]: (history) => {
    if (!history.facetsFilters) {
      return {};
    }
    // we split back the facetsFilters expression to its sub components
    // parameter value is facet1:(value1 OR value2) AND facet2:(value3 OR value4)
    // but beware quotes: facet1:"en:value1"
    const selectedTermsByFacet = history.facetsFilters
      .split(QueryOperator.AND)
      .reduce((acc, filter) => {
        const [key, ...values] = filter.split(':');
        // keep last parts
        let value = values.join(':');
        // remove parenthesis if any
        value = value.replace(/^\((.*)\)$/, '$1');
        acc[key] = acc[key] || [];
        value.split(QueryOperator.OR).forEach((value) => {
          acc[key].push(removeParenthesis(value));
        });
        return acc;
      }, {} as Record<string, string[]>);

    return {
      selectedTermsByFacet,
    };
  },
};
/**
 * Mixin to handle the history of the search
 * It exists to have the logic of the history in a single place
 * It has to be inherited by SearchaliciousSearchMixin to implement relatedFacets and _facetsFilters functionss
 * @param superClass
 * @constructor
 */
export const SearchaliciousHistoryMixin = <T extends Constructor<LitElement>>(
  superClass: T
) => {
  class SearchaliciousHistoryMixinClass extends superClass {
    // stub methods really defined in search-ctl
    @property({attribute: false})
    query = '';
    @property()
    name = DEFAULT_SEARCH_NAME;

    // stub methods defined in search-ctl
    _sortElement = (): SearchaliciousSort | null => {
      throw new Error('Method not implemented.');
    };
    relatedFacets = (): SearchaliciousFacets[] => {
      throw new Error('Method not implemented.');
    };
    _facetsFilters = (): string => {
      throw new Error('Method not implemented.');
    };

    /**
     * Convert the URL params to the original values
     * It will be used to set the values from the URL
     * @param params
     */
    convertHistoryParamsToValues = (params: URLSearchParams): HistoryOutput => {
      const values: HistoryOutput = {history: {}};
      const history = removeParamPrefixes(
        Object.fromEntries(params),
        this.name
      );
      // process each entry using it's specific function in HISTORY_VALUES
      for (const key of SEARCH_PARAMS) {
        Object.assign(values, HISTORY_VALUES[key](history));
      }
      values.history = history;
      return values;
    };

    /**
     * Set the values from the history
     * It will set the params from the URL params
     * @param values
     */
    setValuesFromHistory = (values: HistoryOutput) => {
      this.query = values.query ?? '';
      this._sortElement()?.setSortOptionById(values.sortOptionId);
      // set facets terms using linked facets nodes
      if (values.selectedTermsByFacet) {
        this.relatedFacets().forEach((facets) =>
          facets.setSelectedTermsByFacet(values.selectedTermsByFacet!)
        );
      }
    };

    /**
     * Build the history params from the current state
     * It will be used to update the URL when searching
     * @param params
     */
    buildHistoryParams = (params: SearchParameters) => {
      const urlParams: Record<string, string | undefined | null> = {
        [HistorySearchParams.QUERY]: this.query,
        [HistorySearchParams.SORT_BY]: this._sortElement()?.getSortOptionId(),
        [HistorySearchParams.FACETS_FILTERS]: this._facetsFilters(),
        [HistorySearchParams.PAGE]: params.page,
      };
      // remove empty elements
      Object.keys(urlParams).forEach((key) => {
        if (isNullOrUndefined(urlParams[key])) {
          delete urlParams[key];
        }
      });
      return addParamPrefixes(urlParams, this.name) as HistoryParams;
    };

    /**
     * Set the values from the URL
     * It will set the values from the URL and return if a search should be launched
     */
    setParamFromUrl = () => {
      const params = new URLSearchParams(window.location.search);
      const values = this.convertHistoryParamsToValues(params);

      this.setValuesFromHistory(values);

      const launchSearch = !!Object.entries(values.history).length;
      return {
        launchSearch,
        values,
      };
    };
  }

  return SearchaliciousHistoryMixinClass as Constructor<SearchaliciousHistoryInterface> &
    T;
};
