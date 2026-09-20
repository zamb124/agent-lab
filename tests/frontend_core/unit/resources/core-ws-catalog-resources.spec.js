/**
 * Контракт WS-фабрик в core/events/resources, которые иначе не импортируются unit-сьютом.
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { agentToolkitsListOp } from '@platform/lib/events/resources/flows-agent-toolkits.resource.js';
import { flowsListOp } from '@platform/lib/events/resources/flows-flows-list.resource.js';
import { catalogItemsOp } from '@platform/lib/events/resources/office-catalog-items.resource.js';
import {
    catalogsListOp,
    documentsListOp,
    documentsSearchOp,
} from '@platform/lib/events/resources/office-documents-browse.resource.js';
import { workQueuesResource } from '@platform/lib/events/resources/work-queues.resource.js';
import { resetFactories } from '../../helpers/factory-fixtures.js';

beforeEach(() => {
    resetFactories();
});

afterEach(() => {
    resetFactories();
});

describe('core WS catalog resources', () => {
    it('flows/agent_toolkits', () => {
        expect(agentToolkitsListOp.transport).toBe('ws');
        expect(agentToolkitsListOp.commandType).toBe('flows/agent_toolkits/list_requested');
        expect(agentToolkitsListOp.restMirror).toEqual({
            method: 'GET',
            path: '/flows/api/v1/agent/toolkits/manage',
        });
    });

    it('flows/flows_list', () => {
        expect(flowsListOp.transport).toBe('ws');
        expect(flowsListOp.commandType).toBe('flows/flows/list_requested');
        expect(flowsListOp.restMirror).toEqual({
            method: 'GET',
            path: '/flows/api/v1/flows/',
        });
    });

    it('office catalog browse ops', () => {
        expect(catalogItemsOp.commandType).toBe('office/catalogs/items_requested');
        expect(catalogItemsOp.restMirror).toEqual({
            method: 'GET',
            path: '/documents/api/v1/catalogs/:catalog_id/items',
        });
        expect(catalogsListOp.commandType).toBe('office/catalogs/list_requested');
        expect(catalogsListOp.restMirror).toEqual({
            method: 'GET',
            path: '/documents/api/v1/catalogs',
        });
        expect(documentsListOp.commandType).toBe('office/documents/list_requested');
        expect(documentsListOp.restMirror).toEqual({
            method: 'GET',
            path: '/documents/api/v1/documents',
        });
        expect(documentsSearchOp.commandType).toBe('office/documents/search_requested');
        expect(documentsSearchOp.restMirror).toEqual({
            method: 'GET',
            path: '/documents/api/v1/documents/search',
        });
        expect(catalogItemsOp.transport).toBe('ws');
        expect(catalogsListOp.transport).toBe('ws');
        expect(documentsListOp.transport).toBe('ws');
        expect(documentsSearchOp.transport).toBe('ws');
    });

    it('worktracker/work_queues', () => {
        expect(workQueuesResource.transport).toBe('ws');
        expect(workQueuesResource.idField).toBe('work_queue_id');
        expect(workQueuesResource.restMirror.list).toEqual({
            method: 'GET',
            path: '/worktracker/api/v1/work-queues',
        });
        expect(workQueuesResource.restMirror.create).toEqual({
            method: 'POST',
            path: '/worktracker/api/v1/work-queues',
        });
    });
});
