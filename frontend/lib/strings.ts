export const strings = {
    faceMatch: {
        unverified: 'UNVERIFIED',
        highConfidence: 'HIGH CONFIDENCE',
        partialMatch: 'PARTIAL MATCH',
        photosAnalyzed: (count: number) => `${count} platform photos cross-analyzed.`,
        pairwiseTitle: 'Pairwise DeepFace Analysis',
        noComparison: 'No successful comparison could be made.',
    },
    versionHistory: {
        changeReport: 'Change Report',
        scanRecords: (count: number) => `${count} scan records`,
        versionHistory: 'Version History',
        noChanges: 'No changes detected — Profile data is identical to previous scan.',
    },
} as const;
