/**
 * Tests for the API service module.
 *
 * axios.create is called at module load time so the mock must be in place
 * before the import runs.  We define the mock instance inside the factory
 * (to avoid TDZ issues with const hoisting) and retrieve it via
 * axios.create's mock results.
 */

jest.mock('axios', () => {
  const instance = {
    post: jest.fn(),
    get: jest.fn(),
    delete: jest.fn(),
    interceptors: {
      request: { use: jest.fn() },
      response: { use: jest.fn() },
    },
  };
  return {
    __esModule: true,
    default: { create: jest.fn(() => instance) },
  };
});

import axios from 'axios';
import {
  searchPerson,
  saveProfile,
  getAllProfiles,
  getProfile,
  deleteProfile,
  exportPdfFromData,
  exportJsonFromData,
  exportCsvFromData,
  getSearchHistory,
  getAgentTools,
  getApiHeaders,
  API_BASE_URL,
} from '@/services/api';

// Grab the mock instance that api.ts received from axios.create()
const mock = (axios.create as jest.Mock).mock.results[0].value;

beforeEach(() => {
  mock.post.mockReset();
  mock.get.mockReset();
  mock.delete.mockReset();
});

describe('api', () => {
  describe('axios instance creation', () => {
    it('creates axios with correct baseURL and timeout', () => {
      expect(axios.create).toHaveBeenCalledWith(
        expect.objectContaining({
          baseURL: 'http://localhost:8000',
          timeout: 120_000,
        })
      );
    });

    it('exports API_BASE_URL', () => {
      expect(API_BASE_URL).toBe('http://localhost:8000');
    });
  });

  describe('getApiHeaders', () => {
    it('returns Content-Type when no API key is set', () => {
      const headers = getApiHeaders();
      expect(headers['Content-Type']).toBe('application/json');
      expect(headers['X-API-Key']).toBeUndefined();
    });
  });

  describe('searchPerson', () => {
    it('posts to /api/search/ with query, depth, and extended timeout', async () => {
      const mockData = { name: 'John', ai_response: 'test' };
      mock.post.mockResolvedValueOnce({ data: mockData });

      const result = await searchPerson('John Doe', 5);

      expect(mock.post).toHaveBeenCalledWith(
        '/api/search/',
        { query: 'John Doe', depth: 5 },
        expect.objectContaining({ timeout: 300_000 })
      );
      expect(result).toEqual(mockData);
    });

    it('uses default depth of 5', async () => {
      mock.post.mockResolvedValueOnce({ data: {} });

      await searchPerson('test');

      expect(mock.post).toHaveBeenCalledWith(
        '/api/search/',
        { query: 'test', depth: 5 },
        expect.anything()
      );
    });

    it('passes AbortSignal when provided', async () => {
      mock.post.mockResolvedValueOnce({ data: {} });
      const controller = new AbortController();

      await searchPerson('test', 3, controller.signal);

      expect(mock.post).toHaveBeenCalledWith(
        '/api/search/',
        { query: 'test', depth: 3 },
        expect.objectContaining({ signal: controller.signal })
      );
    });

    it('propagates errors', async () => {
      mock.post.mockRejectedValueOnce(new Error('Network Error'));
      await expect(searchPerson('test')).rejects.toThrow('Network Error');
    });
  });

  describe('saveProfile', () => {
    it('posts to /api/profiles/', async () => {
      const profile = { name: 'Jane' } as any;
      mock.post.mockResolvedValueOnce({ data: profile });

      const result = await saveProfile(profile);

      expect(mock.post).toHaveBeenCalledWith('/api/profiles/', profile);
      expect(result).toEqual(profile);
    });
  });

  describe('getAllProfiles', () => {
    it('gets from /api/profiles/', async () => {
      const profiles = [{ name: 'A' }, { name: 'B' }];
      mock.get.mockResolvedValueOnce({ data: profiles });

      const result = await getAllProfiles();

      expect(mock.get).toHaveBeenCalledWith('/api/profiles/');
      expect(result).toEqual(profiles);
    });
  });

  describe('getProfile', () => {
    it('gets from /api/profiles/:id', async () => {
      const profile = { id: 42, name: 'Test' };
      mock.get.mockResolvedValueOnce({ data: profile });

      const result = await getProfile(42);

      expect(mock.get).toHaveBeenCalledWith('/api/profiles/42');
      expect(result).toEqual(profile);
    });
  });

  describe('deleteProfile', () => {
    it('deletes /api/profiles/:id', async () => {
      mock.delete.mockResolvedValueOnce({});
      await deleteProfile(7);
      expect(mock.delete).toHaveBeenCalledWith('/api/profiles/7');
    });
  });

  describe('export endpoints', () => {
    it('exportPdfFromData posts with responseType blob', async () => {
      const blob = new Blob(['pdf']);
      mock.post.mockResolvedValueOnce({ data: blob });
      const profileData = { name: 'Test' } as any;

      const result = await exportPdfFromData(profileData);

      expect(mock.post).toHaveBeenCalledWith(
        '/api/export/pdf',
        profileData,
        { responseType: 'blob' }
      );
      expect(result).toBe(blob);
    });

    it('exportJsonFromData posts with responseType blob', async () => {
      mock.post.mockResolvedValueOnce({ data: new Blob(['json']) });
      await exportJsonFromData({} as any);
      expect(mock.post).toHaveBeenCalledWith(
        '/api/export/json',
        expect.anything(),
        { responseType: 'blob' }
      );
    });

    it('exportCsvFromData posts with responseType blob', async () => {
      mock.post.mockResolvedValueOnce({ data: new Blob(['csv']) });
      await exportCsvFromData({} as any);
      expect(mock.post).toHaveBeenCalledWith(
        '/api/export/csv',
        expect.anything(),
        { responseType: 'blob' }
      );
    });
  });

  describe('getSearchHistory', () => {
    it('gets from /api/history/', async () => {
      const items = [{ id: 1, query: 'test' }];
      mock.get.mockResolvedValueOnce({ data: items });

      const result = await getSearchHistory();

      expect(mock.get).toHaveBeenCalledWith('/api/history/');
      expect(result).toEqual(items);
    });
  });

  describe('getAgentTools', () => {
    it('gets tools from /api/agent/tools', async () => {
      const tools = [{ name: 'search', description: 'Search tool' }];
      mock.get.mockResolvedValueOnce({ data: { tools } });

      const result = await getAgentTools();

      expect(mock.get).toHaveBeenCalledWith('/api/agent/tools');
      expect(result).toEqual(tools);
    });
  });
});
