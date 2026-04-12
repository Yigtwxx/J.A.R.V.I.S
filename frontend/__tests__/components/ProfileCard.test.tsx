import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

// Mock framer-motion
jest.mock('framer-motion', () => ({
  motion: new Proxy({}, {
    get: (_target, prop) => {
      return React.forwardRef((props: any, ref: any) => {
        const { initial, animate, transition, whileHover, whileTap, ...rest } = props;
        return React.createElement(prop as string, { ...rest, ref });
      });
    },
  }),
  AnimatePresence: ({ children }: any) => children,
}));

// Mock next/dynamic
jest.mock('next/dynamic', () => {
  return () => {
    return function MockDynamic(props: any) {
      return <div data-testid="dynamic-component" />;
    };
  };
});

// Mock GlitchText
jest.mock('@/components/ui/GlitchText', () => {
  return function MockGlitchText({ text }: { text: string }) {
    return <span>{text}</span>;
  };
});

// Mock api exports
const mockExportPdf = jest.fn();
const mockExportJson = jest.fn();
const mockExportCsv = jest.fn();
jest.mock('@/services/api', () => ({
  exportPdfFromData: (...args: any[]) => mockExportPdf(...args),
  exportJsonFromData: (...args: any[]) => mockExportJson(...args),
  exportCsvFromData: (...args: any[]) => mockExportCsv(...args),
}));

// Mock toast
const mockShowError = jest.fn();
jest.mock('@/lib/toast', () => ({
  showError: (...args: any[]) => mockShowError(...args),
}));

// Mock lucide-react icons
jest.mock('lucide-react', () => ({
  User: (props: any) => <svg data-testid="user-icon" {...props} />,
  Users: (props: any) => <svg data-testid="users-icon" {...props} />,
  ChevronRight: (props: any) => <svg data-testid="chevron-icon" {...props} />,
  Activity: (props: any) => <svg data-testid="activity-icon" {...props} />,
  AlertTriangle: (props: any) => <svg data-testid="alert-icon" {...props} />,
  FileText: (props: any) => <svg data-testid="file-text-icon" {...props} />,
  FileJson: (props: any) => <svg data-testid="file-json-icon" {...props} />,
  FileSpreadsheet: (props: any) => <svg data-testid="file-spreadsheet-icon" {...props} />,
  Download: (props: any) => <svg data-testid="download-icon" {...props} />,
}));

import ProfileCard from '@/components/ProfileCard';
import type { SearchResponse } from '@/types/profile';

// Mock URL.createObjectURL and URL.revokeObjectURL
global.URL.createObjectURL = jest.fn(() => 'blob:mock-url');
global.URL.revokeObjectURL = jest.fn();

const baseProfile: SearchResponse = {
  name: 'John Doe',
  ai_response: 'Test response',
  description: 'A test description for John Doe.',
  cross_validation_issues: [],
  similar_profiles: [],
  email_addresses: [],
  data_breaches: [],
  network_connections: [],
} as any;

beforeEach(() => {
  jest.clearAllMocks();
});

describe('ProfileCard', () => {
  it('renders profile name', () => {
    render(<ProfileCard profile={baseProfile} />);
    expect(screen.getByText('John Doe')).toBeInTheDocument();
  });

  it('renders description', () => {
    render(<ProfileCard profile={baseProfile} />);
    expect(screen.getByText('A test description for John Doe.')).toBeInTheDocument();
  });

  it('renders "Extracted Bio" section header', () => {
    render(<ProfileCard profile={baseProfile} />);
    expect(screen.getByText('Extracted Bio')).toBeInTheDocument();
  });

  it('does not render description section when description is empty', () => {
    const profile = { ...baseProfile, description: '' };
    render(<ProfileCard profile={profile} />);
    expect(screen.queryByText('Extracted Bio')).not.toBeInTheDocument();
  });

  it('renders cross-validation issues', () => {
    const profile = {
      ...baseProfile,
      cross_validation_issues: ['Name mismatch found', 'Location inconsistency'],
    };
    render(<ProfileCard profile={profile} />);

    expect(screen.getByText('Data Integrity Warning')).toBeInTheDocument();
    expect(screen.getByText('Name mismatch found')).toBeInTheDocument();
    expect(screen.getByText('Location inconsistency')).toBeInTheDocument();
  });

  it('does not render warning section when no issues', () => {
    render(<ProfileCard profile={baseProfile} />);
    expect(screen.queryByText('Data Integrity Warning')).not.toBeInTheDocument();
  });

  it('renders correlated targets (similar_profiles)', () => {
    const profile = {
      ...baseProfile,
      similar_profiles: ['Alice Smith', 'Bob Jones'],
    };
    render(<ProfileCard profile={profile} />);

    expect(screen.getByText('Correlated Targets')).toBeInTheDocument();
    expect(screen.getByText('Alice Smith')).toBeInTheDocument();
    expect(screen.getByText('Bob Jones')).toBeInTheDocument();
  });

  it('does not render correlated targets when empty', () => {
    render(<ProfileCard profile={baseProfile} />);
    expect(screen.queryByText('Correlated Targets')).not.toBeInTheDocument();
  });

  it('renders "Unknown" when profile name is empty', () => {
    const profile = { ...baseProfile, name: '' };
    render(<ProfileCard profile={profile} />);
    expect(screen.getByText('Unknown')).toBeInTheDocument();
  });

  describe('export functionality', () => {
    it('shows export button', () => {
      render(<ProfileCard profile={baseProfile} />);
      expect(screen.getByText('Export')).toBeInTheDocument();
    });

    it('opens export dropdown on click', async () => {
      const user = userEvent.setup();
      render(<ProfileCard profile={baseProfile} />);

      await user.click(screen.getByText('Export'));

      expect(screen.getByText('PDF Dossier')).toBeInTheDocument();
      expect(screen.getByText('JSON Intel')).toBeInTheDocument();
      expect(screen.getByText('CSV Data')).toBeInTheDocument();
    });

    it('calls exportPdfFromData on PDF export', async () => {
      const user = userEvent.setup();
      mockExportPdf.mockResolvedValueOnce(new Blob(['pdf-content']));

      render(<ProfileCard profile={baseProfile} />);

      await user.click(screen.getByText('Export'));
      await user.click(screen.getByText('PDF Dossier'));

      await waitFor(() => {
        expect(mockExportPdf).toHaveBeenCalledWith(baseProfile);
        expect(global.URL.createObjectURL).toHaveBeenCalled();
      });
    });

    it('calls exportJsonFromData on JSON export', async () => {
      const user = userEvent.setup();
      mockExportJson.mockResolvedValueOnce(new Blob(['json']));

      render(<ProfileCard profile={baseProfile} />);
      await user.click(screen.getByText('Export'));
      await user.click(screen.getByText('JSON Intel'));

      await waitFor(() => {
        expect(mockExportJson).toHaveBeenCalledWith(baseProfile);
      });
    });

    it('shows error toast on export failure', async () => {
      const user = userEvent.setup();
      mockExportPdf.mockRejectedValueOnce(new Error('Server Error'));

      render(<ProfileCard profile={baseProfile} />);

      await user.click(screen.getByText('Export'));
      await user.click(screen.getByText('PDF Dossier'));

      await waitFor(() => {
        expect(mockShowError).toHaveBeenCalledWith('Export failed. Please try again.');
      });
    });
  });
});
