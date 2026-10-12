import type { DataProvider, HttpError } from '@refinedev/core'

const unsupported = (operation: string) => () =>
  Promise.reject<never>({
    message: `${operation} is not available yet`,
    statusCode: 501,
  } satisfies HttpError)

// Same-origin backend API. Resource methods are added with the views that need them.
export const dataProvider: DataProvider = {
  getApiUrl: () => '/api',
  custom: async ({ url, method, payload }) => {
    let response: Response
    try {
      response = await fetch(url, {
        method,
        headers: {
          Accept: 'application/json',
          ...(payload === undefined ? {} : { 'Content-Type': 'application/json' }),
        },
        body: payload === undefined ? undefined : JSON.stringify(payload),
      })
    } catch {
      throw { message: 'The backend is unreachable', statusCode: 0 } satisfies HttpError
    }
    if (!response.ok) {
      throw {
        message: `The backend answered ${response.status}`,
        statusCode: response.status,
      } satisfies HttpError
    }
    return { data: await response.json() }
  },
  getList: unsupported('getList'),
  getOne: unsupported('getOne'),
  create: unsupported('create'),
  update: unsupported('update'),
  deleteOne: unsupported('deleteOne'),
}
